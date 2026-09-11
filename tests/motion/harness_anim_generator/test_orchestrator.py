from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from conftest import FakeAgentProvider, client_for, create_outputs
from motion2sheet.motion.harness_anim_generator.contracts import GenerationRequest, HarnessError
from motion2sheet.motion.harness_anim_generator.orchestrator import AnimationGenerationOrchestrator


def orchestrator(repo: Path, tmp_path: Path, provider, **kwargs):
    return AnimationGenerationOrchestrator(
        provider=provider,
        repo_root=repo,
        workspace_root=tmp_path / "runs",
        **kwargs,
    )


def successful_behavior(request, session, *, incomplete_skill: bool = False, marker: bytes = b"v1"):
    client = client_for(request)
    client.send("agent.started")
    client.send("iteration.started", iteration=1, payload={"reason": "Initial authoring"})
    client.send(
        "skill.step.completed",
        iteration=1,
        payload={"step": "understand-intent", "summary": "Intent understood"},
    )
    client.send(
        "skill.step.skipped",
        iteration=1,
        payload={"step": "refine", "reason": "No refinement needed"},
    )
    evidence = request.workspace / "notes.txt"
    evidence.write_text("opaque evidence", encoding="utf-8")
    client.send("evidence.created", iteration=1, payload={"path": "notes.txt"})
    client.send("iteration.completed", iteration=1, payload={"summary": "Agent iteration done"})
    outputs = create_outputs(request.workspace, marker)
    client.send("agent.completed", payload={"outputs": outputs})
    session.finish(0)


def test_full_prompt_skill_agent_events_and_outputs(repo_with_skill, tmp_path):
    provider = FakeAgentProvider(successful_behavior)
    output = tmp_path / "published"
    result = orchestrator(repo_with_skill, tmp_path, provider).run(
        GenerationRequest("exact user prompt", "fake-agent", output, open_report=False)
    )
    sent = provider.requests[0]
    assert sent.prompt == "exact user prompt"
    assert sent.skill_text == (
        repo_with_skill / "skills/humanoid-motion-local-authoring/SKILL.md"
    ).read_text(encoding="utf-8")
    assert sent.skill_manifest.id == "humanoid-motion-local-authoring"
    assert not hasattr(sent, "selected_reference")
    assert {path.name for path in output.iterdir()} == {
        "animation.json",
        "metadata.json",
        "preview.gif",
    }
    assert result.status == "completed"
    state = json.loads((result.workspace / "run.json").read_text())
    assert state["status"] == "completed"
    assert state["skillSteps"]["1"]["refine"]["status"] == "skipped"
    assert state["skillSteps"]["1"]["understand-intent"]["status"] == "completed"
    assert state["skillSteps"]["1"].get("discover-references") is None
    assert state["evidence"][0]["name"] == "notes.txt"
    assert result.report_path.is_file()


def test_two_agent_owned_iterations_are_preserved(repo_with_skill, tmp_path):
    def behavior(request, session):
        client = client_for(request)
        client.send("iteration.started", iteration=1, payload={"reason": "draft"})
        first = request.workspace / "first.txt"
        first.write_text("first", encoding="utf-8")
        client.send("artifact.created", iteration=1, payload={"path": "first.txt"})
        client.send("iteration.completed", iteration=1, payload={"summary": "reviewed"})
        client.send("iteration.started", iteration=2, payload={"reason": "agent chose refinement"})
        second = request.workspace / "second.txt"
        second.write_text("second", encoding="utf-8")
        client.send("artifact.created", iteration=2, payload={"path": "second.txt"})
        client.send("iteration.completed", iteration=2, payload={"summary": "accepted"})
        client.send("agent.completed", payload={"outputs": create_outputs(request.workspace, b"v2")})
        session.finish(0)

    result = orchestrator(repo_with_skill, tmp_path, FakeAgentProvider(behavior)).run(
        GenerationRequest("attack", "fake", tmp_path / "out", open_report=False)
    )
    history = json.loads((result.workspace / "history.json").read_text())
    assert [item["iteration"] for item in history["iterations"]] == [1, 2]
    assert [item["name"] for item in history["artifacts"]] == ["first.txt", "second.txt"]
    assert (result.workspace / "iterations/v1/artifacts").is_dir()
    assert (result.workspace / "iterations/v2/artifacts").is_dir()
    assert (tmp_path / "out/animation.json").read_bytes() == b'{"opaque":"v2"}'


def test_resume_creates_new_run_and_does_not_mutate_parent(repo_with_skill, tmp_path):
    first_provider = FakeAgentProvider(successful_behavior)
    first = orchestrator(repo_with_skill, tmp_path, first_provider).run(
        GenerationRequest("original", "fake", tmp_path / "out1", open_report=False)
    )
    before = {p.relative_to(first.workspace): p.read_bytes() for p in first.workspace.rglob("*") if p.is_file()}
    second_provider = FakeAgentProvider(successful_behavior)
    second = orchestrator(repo_with_skill, tmp_path, second_provider).run(
        GenerationRequest(
            "continue",
            "fake",
            tmp_path / "out2",
            resume_run_id=first.run_id,
            open_report=False,
        )
    )
    assert second.run_id != first.run_id
    assert second.parent_run_id == first.run_id
    assert second_provider.requests[0].history["originalPrompt"] == "original"
    after = {p.relative_to(first.workspace): p.read_bytes() for p in first.workspace.rglob("*") if p.is_file()}
    assert after == before


@pytest.mark.parametrize("mode", ["reported", "nonzero", "missing-completion"])
def test_terminal_failures_preserve_diagnostics_without_publish(repo_with_skill, tmp_path, mode):
    def behavior(request, session):
        client = client_for(request)
        client.send("agent.started")
        note = request.workspace / "note.txt"
        note.write_text("kept", encoding="utf-8")
        client.send("artifact.created", payload={"path": "note.txt"})
        if mode == "reported":
            client.send("agent.failed", payload={"message": "agent stopped"})
            session.finish(0)
        elif mode == "nonzero":
            session.finish(7)
        else:
            session.finish(0)

    provider = FakeAgentProvider(behavior)
    runtime = orchestrator(repo_with_skill, tmp_path, provider)
    active = runtime.start(GenerationRequest("attack", "fake", tmp_path / "out", open_report=False))
    with pytest.raises(HarnessError):
        active.wait()
    assert not (tmp_path / "out").exists()
    assert (active.workspace.logs / "events.jsonl").is_file()
    assert (active.workspace.root / "history.json").is_file()
    assert (active.workspace.report / "index.html").is_file()


def test_heartbeat_updates_liveness_without_domain_polling(repo_with_skill, tmp_path):
    release = threading.Event()

    def behavior(request, session):
        client = client_for(request)
        client.send("agent.started")
        client.send("agent.heartbeat", payload={"message": "alive"})
        release.wait(5)
        client.send("agent.completed", payload={"outputs": create_outputs(request.workspace)})
        session.finish(0)

    active = orchestrator(repo_with_skill, tmp_path, FakeAgentProvider(behavior)).start(
        GenerationRequest("attack", "fake", tmp_path / "out", open_report=False)
    )
    deadline = time.monotonic() + 2
    while active.state.snapshot()["lastHeartbeat"] is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert active.state.snapshot()["agentAliveState"] == "running"
    assert active.state.snapshot()["pid"] == 4242
    release.set()
    assert active.wait().status == "completed"


def test_missing_skill_fails_before_provider_launch(tmp_path):
    provider = FakeAgentProvider(successful_behavior)
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(HarnessError, match="skill file is missing"):
        orchestrator(repo, tmp_path, provider).start(
            GenerationRequest("attack", "fake", tmp_path / "out", open_report=False)
        )
    assert provider.requests == []


def test_malformed_skill_fails_before_provider_launch(tmp_path):
    provider = FakeAgentProvider(successful_behavior)
    repo = tmp_path / "repo"
    skill = repo / "skills/humanoid-motion-local-authoring"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("real workflow", encoding="utf-8")
    (skill / "skill.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(HarnessError, match="cannot load skill"):
        orchestrator(repo, tmp_path, provider).start(
            GenerationRequest("attack", "fake", tmp_path / "out", open_report=False)
        )
    assert provider.requests == []


def test_completion_waits_for_process_exit_and_queue_drain(repo_with_skill, tmp_path):
    processor_gate = threading.Event()
    process_gate = threading.Event()

    def slow(event):
        if event.event_type == "agent.completed":
            processor_gate.wait(5)

    def behavior(request, session):
        client_for(request).send(
            "agent.completed", payload={"outputs": create_outputs(request.workspace)}
        )
        process_gate.wait(5)
        session.finish(0)

    active = orchestrator(
        repo_with_skill,
        tmp_path,
        FakeAgentProvider(behavior),
        processing_hook=slow,
    ).start(GenerationRequest("attack", "fake", tmp_path / "out", open_report=False))
    holder = {}
    waiter = threading.Thread(target=lambda: holder.setdefault("result", active.wait()), daemon=True)
    waiter.start()
    time.sleep(0.05)
    assert not (tmp_path / "out").exists()
    process_gate.set()
    time.sleep(0.05)
    assert not (tmp_path / "out").exists()
    processor_gate.set()
    waiter.join(5)
    assert holder["result"].status == "completed"
    assert (tmp_path / "out/animation.json").is_file()
