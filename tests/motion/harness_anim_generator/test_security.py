from __future__ import annotations

import threading
import urllib.request
from pathlib import Path

import pytest

from conftest import FakeAgentProvider, client_for, create_outputs
from motion2sheet.motion.harness_anim_generator.contracts import (
    GenerationRequest,
    OutputContractError,
    ProviderEvent,
)
from motion2sheet.motion.harness_anim_generator.orchestrator import AnimationGenerationOrchestrator


def runtime(repo, tmp_path, provider):
    return AnimationGenerationOrchestrator(
        provider=provider,
        repo_root=repo,
        workspace_root=tmp_path / "runs",
    )


def test_token_is_redacted_from_all_disk_and_report_sinks(repo_with_skill, tmp_path):
    captured = {}

    def behavior(request, session):
        token = request.event_token
        captured["token"] = token.encode()
        session.emit_provider(
            ProviderEvent(
                "agent.log",
                {"message": f"provider echoed {token}"},
                raw=f"HARNESS_TOKEN={token}",
                stream="stdout",
            )
        )
        session.emit_provider(
            ProviderEvent("agent.log", {"message": token}, raw=token, stream="stderr")
        )
        client = client_for(request)
        client.send("agent.log", payload={"message": f"env says {token}"})
        client.send("agent.completed", payload={"outputs": create_outputs(request.workspace)})
        session.finish(0)

    result = runtime(repo_with_skill, tmp_path, FakeAgentProvider(behavior)).run(
        GenerationRequest("attack", "fake", tmp_path / "out", open_report=False)
    )
    token = captured["token"]
    checked = []
    for path in result.workspace.rglob("*"):
        if path.is_file() and not path.is_symlink():
            checked.append(path)
            assert token not in path.read_bytes(), path
    assert checked
    assert b"[REDACTED]" in (result.workspace / "logs/stdout.log").read_bytes()
    assert b"[REDACTED]" in (result.workspace / "logs/stderr.log").read_bytes()
    assert b"[REDACTED]" in (result.workspace / "logs/events.jsonl").read_bytes()
    assert b"[REDACTED]" in (result.workspace / "logs/provider-events.jsonl").read_bytes()
    assert b"[REDACTED]" in (result.workspace / "report/app.js").read_bytes()


def test_realtime_snapshot_redacts_token_while_agent_is_running(repo_with_skill, tmp_path):
    release = threading.Event()
    emitted = threading.Event()
    captured = {}

    def behavior(request, session):
        captured["token"] = request.event_token.encode()
        client_for(request).send(
            "agent.log", payload={"message": f"printenv: {request.event_token}"}
        )
        emitted.set()
        release.wait(5)
        client_for(request).send(
            "agent.completed", payload={"outputs": create_outputs(request.workspace)}
        )
        session.finish(0)

    active = runtime(repo_with_skill, tmp_path, FakeAgentProvider(behavior)).start(
        GenerationRequest("attack", "fake", tmp_path / "out", open_report=False)
    )
    assert emitted.wait(2)
    active.processor.drain()
    with urllib.request.urlopen(active.report_url + "snapshot", timeout=2) as response:
        snapshot = response.read()
    assert captured["token"] not in snapshot
    assert b"[REDACTED]" in snapshot
    release.set()
    active.wait()


@pytest.mark.parametrize("escape", ["traversal", "absolute", "symlink"])
def test_completion_rejects_paths_outside_agent_workspace(repo_with_skill, tmp_path, escape):
    outside = tmp_path / "outside.json"
    outside.write_text("secret host data", encoding="utf-8")

    def behavior(request, session):
        outputs = create_outputs(request.workspace)
        if escape == "traversal":
            outputs["animation"] = "../../outside.json"
        elif escape == "absolute":
            outputs["animation"] = str(outside)
        else:
            link = request.workspace / "escape.json"
            link.symlink_to(outside)
            outputs["animation"] = "escape.json"
        client_for(request).send("agent.completed", payload={"outputs": outputs})
        session.finish(0)

    active = runtime(repo_with_skill, tmp_path, FakeAgentProvider(behavior)).start(
        GenerationRequest("attack", "fake", tmp_path / "out", open_report=False)
    )
    with pytest.raises(OutputContractError, match="escapes|non-symlink"):
        active.wait()
    assert not (tmp_path / "out").exists()


def test_invalid_artifact_observation_warns_but_does_not_fail_run(repo_with_skill, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("host", encoding="utf-8")

    def behavior(request, session):
        client = client_for(request)
        client.send("artifact.created", payload={"path": str(outside)})
        client.send("artifact.read", payload={"path": str(outside)})
        client.send("agent.completed", payload={"outputs": create_outputs(request.workspace)})
        session.finish(0)

    result = runtime(repo_with_skill, tmp_path, FakeAgentProvider(behavior)).run(
        GenerationRequest("attack", "fake", tmp_path / "out", open_report=False)
    )
    run = (result.workspace / "run.json").read_text(encoding="utf-8")
    assert "artifact escapes agent workspace" in run
    assert outside.read_text() == "host"
    snapshots = list((result.workspace / "iterations").rglob("outside.txt"))
    assert snapshots == []


def test_output_containing_runtime_token_is_rejected(repo_with_skill, tmp_path):
    def behavior(request, session):
        outputs = create_outputs(request.workspace)
        (request.workspace / outputs["animation"]).write_text(request.event_token, encoding="utf-8")
        client_for(request).send("agent.completed", payload={"outputs": outputs})
        session.finish(0)

    active = runtime(repo_with_skill, tmp_path, FakeAgentProvider(behavior)).start(
        GenerationRequest("attack", "fake", tmp_path / "out", open_report=False)
    )
    with pytest.raises(OutputContractError, match="runtime secret"):
        active.wait()


@pytest.mark.parametrize("mode", ["missing", "empty"])
def test_completed_declaration_requires_existing_nonempty_files(repo_with_skill, tmp_path, mode):
    def behavior(request, session):
        outputs = create_outputs(request.workspace)
        animation = request.workspace / outputs["animation"]
        if mode == "missing":
            animation.unlink()
        else:
            animation.write_bytes(b"")
        client_for(request).send("agent.completed", payload={"outputs": outputs})
        session.finish(0)

    active = runtime(repo_with_skill, tmp_path, FakeAgentProvider(behavior)).start(
        GenerationRequest("attack", "fake", tmp_path / "out", open_report=False)
    )
    with pytest.raises(OutputContractError, match="does not exist|empty"):
        active.wait()
    assert not (tmp_path / "out").exists()
