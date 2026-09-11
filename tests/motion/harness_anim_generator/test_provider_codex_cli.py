from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from motion2sheet.motion.harness_anim_generator.contracts import (
    ProviderError,
    ProviderRequest,
)
from motion2sheet.motion.harness_anim_generator.providers.codex_cli import CodexCLIProvider


def _request(tmp_path: Path) -> ProviderRequest:
    image = tmp_path / "sheet.png"
    image.write_bytes(b"png")
    return ProviderRequest(
        operation="review",
        instruction="Return a review",
        context={"prompt": "heavy attack"},
        response_schema={"type": "object"},
        attachments=(image,),
    )


def test_codex_cli_builds_command_passes_request_and_parses_jsonl(tmp_path, monkeypatch):
    observed = {}
    payload = {"pass": True, "issues": []}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        schema_path = Path(command[command.index("--output-schema") + 1])
        assert json.loads(schema_path.read_text()) == {"type": "object"}
        stdout = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "thread"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"type": "agent_message", "text": json.dumps(payload)},
                    }
                ),
                json.dumps({"type": "turn.completed"}),
            ]
        )
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(
        "motion2sheet.motion.harness_anim_generator.providers.codex_cli.subprocess.run",
        fake_run,
    )
    response = CodexCLIProvider(repo_root=tmp_path).generate(_request(tmp_path))
    assert response.payload == payload
    assert observed["command"][:2] == [
        "codex",
        "exec",
    ]
    assert "--image" in observed["command"]
    image_index = observed["command"].index("--image")
    assert observed["command"][image_index + 2] == "--ephemeral"
    assert observed["command"][-1] == "-"
    request_input = json.loads(observed["kwargs"]["input"])
    assert request_input["context"]["prompt"] == "heavy attack"
    assert observed["kwargs"]["cwd"] == tmp_path.resolve()
    assert observed["kwargs"]["capture_output"] is True


def test_codex_cli_nonzero_exit_is_provider_error(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "motion2sheet.motion.harness_anim_generator.providers.codex_cli.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=7, stdout="", stderr="auth failed"),
    )
    with pytest.raises(ProviderError, match="code 7.*auth failed"):
        CodexCLIProvider(repo_root=tmp_path).generate(_request(tmp_path))


@pytest.mark.parametrize(
    "stdout, message",
    [
        ("not-json", "malformed JSONL"),
        (json.dumps({"type": "turn.completed"}), "completed agent message"),
        (
            json.dumps(
                {"type": "item.completed", "item": {"type": "agent_message", "text": "nope"}}
            ),
            "final message is not valid JSON",
        ),
    ],
)
def test_codex_cli_malformed_output_fails_clearly(tmp_path, monkeypatch, stdout, message):
    monkeypatch.setattr(
        "motion2sheet.motion.harness_anim_generator.providers.codex_cli.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=stdout, stderr=""),
    )
    with pytest.raises(ProviderError, match=message):
        CodexCLIProvider(repo_root=tmp_path).generate(_request(tmp_path))


def test_codex_cli_timeout_is_provider_error(tmp_path, monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("codex", 1)

    monkeypatch.setattr(
        "motion2sheet.motion.harness_anim_generator.providers.codex_cli.subprocess.run",
        timeout,
    )
    with pytest.raises(ProviderError, match="timed out"):
        CodexCLIProvider(repo_root=tmp_path, timeout_seconds=1).generate(_request(tmp_path))
