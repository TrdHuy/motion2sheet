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


def request(tmp_path: Path) -> AgentRunRequest:
    workspace = tmp_path / "agent"
    notify = workspace / ".sdar/bin/sdar-notify"
    notify.parent.mkdir(parents=True)
    notify.touch()
    return AgentRunRequest(
        run_id="run-1",
        prompt="exact prompt",
        skill_text="# FULL SKILL\nEvery line is authoritative.\n",
        skill_manifest=SkillManifest("skill", 1, (SkillStep("one", "One"),)),
        repository=tmp_path,
        workspace=workspace,
        history={"prior": "history"},
        event_url="http://127.0.0.1:1234/runs/run-1/events",
        event_token="secret-token",
        notify_command=notify,
    )


def test_codex_provider_launches_agent_session_with_full_runtime_context(tmp_path):
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

    run_request = request(tmp_path)
    session = CodexCLIProvider(repo_root=tmp_path, popen_factory=popen).start(run_request)
    assert observed["command"][:2] == ["codex", "exec"]
    assert "--json" in observed["command"]
    assert "--ignore-user-config" in observed["command"]
    assert "workspace-write" in observed["command"]
    assert "sandbox_workspace_write.network_access=true" in observed["command"]
    assert "shell_environment_policy.inherit=all" in observed["command"]
    assert "shell_environment_policy.ignore_default_excludes=true" in observed["command"]
    environment = observed["kwargs"]["env"]
    assert environment["HARNESS_RUN_ID"] == "run-1"
    assert environment["HARNESS_EVENT_URL"] == run_request.event_url
    assert environment["HARNESS_TOKEN"] == "secret-token"
    assert environment["SDAR_NOTIFY"] == str(run_request.notify_command)
    assert run_request.skill_text in process.stdin.value
    assert "exact prompt" in process.stdin.value
    assert '"prior": "history"' in process.stdin.value
    event = session.next_event(timeout=1)
    assert event is not None and event.event_type == "command.completed"


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
