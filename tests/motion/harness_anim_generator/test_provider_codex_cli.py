from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from motion2sheet.motion.harness_anim_generator.contracts import (
    AgentRunRequest,
    ProviderError,
    SkillManifest,
    SkillStep,
)
from motion2sheet.motion.harness_anim_generator.providers.codex_cli import CodexCLIProvider


class InputCapture:
    def __init__(self):
        self.value = ""
        self.closed = False

    def write(self, value):
        self.value += value

    def close(self):
        self.closed = True


class FakeProcess:
    def __init__(self, stdout="", stderr="", code=0):
        self.pid = 99
        self.stdin = InputCapture()
        self.stdout = io.StringIO(stdout)
        self.stderr = io.StringIO(stderr)
        self.code = code
        self.terminated = False

    def poll(self):
        return self.code

    def wait(self, timeout=None):
        return self.code

    def terminate(self):
        self.terminated = True


def request(tmp_path: Path, *, history=None, memory=None) -> AgentRunRequest:
    repository = tmp_path / "repo"
    repository.mkdir(exist_ok=True)
    workspace = tmp_path / "runs" / "current" / "agent"
    notify = workspace / ".sdar/bin/sdar-notify"
    notify.parent.mkdir(parents=True)
    notify.touch()
    return AgentRunRequest(
        run_id="run-1",
        prompt="exact prompt",
        skill_text="# FULL SKILL\nEvery line is authoritative.\n",
        skill_manifest=SkillManifest("skill", 1, (SkillStep("one", "One"),)),
        repository=repository,
        workspace=workspace,
        memory=(
            memory
            if memory is not None
            else {
                "skillId": "skill",
                "skillVersion": 1,
                "provider": "codex-cli",
                "entries": [{"entry": {"statement": "private prior lesson"}}],
            }
        ),
        history=history or {"prior": "history"},
        event_url="http://127.0.0.1:1234/runs/run-1/events",
        event_token="secret-token",
        notify_command=notify,
    )


def test_codex_provider_launches_agent_session_with_isolated_runtime_context(
    tmp_path, monkeypatch
):
    observed = {}
    process = FakeProcess(
        stdout=json.dumps(
            {"type": "item.completed", "item": {"type": "command_execution", "command": "x"}}
        )
        + "\n"
    )

    def popen(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        return process

    monkeypatch.setenv("GH_TOKEN", "host-secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "host-secret-2")
    monkeypatch.setenv("OPENAI_API_KEY", "provider-secret")
    run_request = request(tmp_path)
    session = CodexCLIProvider(repo_root=tmp_path, popen_factory=popen).start(run_request)
    assert observed["command"][:2] == ["codex", "exec"]
    assert "--json" in observed["command"]
    assert "--ignore-user-config" in observed["command"]
    assert "workspace-write" in observed["command"]
    assert "sandbox_workspace_write.network_access=true" in observed["command"]
    assert "sandbox_workspace_write.writable_roots=[]" in observed["command"]
    assert "sandbox_workspace_write.exclude_slash_tmp=true" in observed["command"]
    assert "shell_environment_policy.inherit=all" in observed["command"]
    assert not any("ignore_default_excludes" in item for item in observed["command"])
    filters = next(item for item in observed["command"] if item.startswith("shell_environment_policy.filters="))
    for name in (
        "HARNESS_RUN_ID",
        "HARNESS_EVENT_URL",
        "HARNESS_TOKEN",
        "HARNESS_EVENT_STATE",
        "SDAR_NOTIFY",
        "SDAR_REPOSITORY",
        "PATH",
        "PYTHONPATH",
    ):
        assert f'{name}="include"' in filters
    assert "GH_TOKEN" not in filters
    assert "AWS_SECRET_ACCESS_KEY" not in filters
    assert "OPENAI_API_KEY" not in filters
    assert observed["kwargs"]["cwd"] == run_request.workspace
    assert observed["command"][observed["command"].index("-C") + 1] == str(
        run_request.workspace
    )
    assert str(run_request.repository) not in observed["command"]
    environment = observed["kwargs"]["env"]
    assert environment["HARNESS_RUN_ID"] == "run-1"
    assert environment["HARNESS_EVENT_URL"] == run_request.event_url
    assert environment["HARNESS_TOKEN"] == "secret-token"
    assert environment["SDAR_NOTIFY"] == str(run_request.notify_command)
    assert environment["SDAR_REPOSITORY"] == str(run_request.repository)
    assert environment["PYTHONPATH"] == str(run_request.repository)
    assert environment["TMPDIR"] == str(run_request.workspace / ".tmp")
    assert run_request.skill_text in process.stdin.value
    assert "exact prompt" in process.stdin.value
    assert '"prior": "history"' in process.stdin.value
    assert '"statement":"private prior lesson"' in process.stdin.value
    event = session.next_event(timeout=1)
    assert event is not None and event.event_type == "command.completed"


def test_codex_prompt_requires_sdar_progress_protocol(tmp_path):
    run_request = request(tmp_path)
    prompt = CodexCLIProvider._prompt(run_request)
    for command in (
        "iteration-start",
        "iteration-complete",
        "skill-start",
        "skill-complete",
        "skill-skip",
        "memory-update <path>",
        "complete --animation <path> --metadata <path> --preview <path>",
    ):
        assert command in prompt
    assert run_request.skill_text in prompt
    assert "PROVIDER MEMORY" in prompt
    assert "private prior lesson" in prompt
    compact_memory = json.dumps(
        run_request.memory,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert compact_memory in prompt


def test_resume_history_is_prompt_context_not_a_writable_root(tmp_path):
    old_run = tmp_path / "runs" / "old-run"
    old_run.mkdir(parents=True)
    run_request = request(tmp_path, history={"artifactPaths": [str(old_run / "evidence.png")]})
    provider = CodexCLIProvider(repo_root=run_request.repository)
    command = provider._command(run_request)
    prompt = provider._prompt(run_request)
    assert str(old_run) not in command
    assert str(old_run / "evidence.png") in prompt
    assert "Previous run history and any paths it references are read-only" in prompt


def test_codex_provider_streams_malformed_json_as_warning(tmp_path):
    process = FakeProcess(stdout="not-json\n")
    provider = CodexCLIProvider(repo_root=tmp_path, popen_factory=lambda *a, **k: process)
    session = provider.start(request(tmp_path))
    event = session.next_event(timeout=1)
    assert event is not None
    assert event.event_type == "agent.warning"
    assert event.raw == "not-json"


def test_codex_provider_reports_missing_executable(tmp_path):
    def missing(*_args, **_kwargs):
        raise FileNotFoundError("codex")

    provider = CodexCLIProvider(repo_root=tmp_path, popen_factory=missing)
    with pytest.raises(ProviderError, match="executable not found"):
        provider.start(request(tmp_path))
