from __future__ import annotations

import json
import threading
import time
import urllib.request
import uuid

from conftest import FakeAgentProvider, client_for, create_outputs, post_json
from motion2sheet.motion.harness_anim_generator.contracts import GenerationRequest
from motion2sheet.motion.harness_anim_generator.orchestrator import AnimationGenerationOrchestrator


def blocking_run(repo_with_skill, tmp_path, *, processing_hook=None):
    release = threading.Event()

    def behavior(request, session):
        client_for(request).send("agent.started")
        release.wait(5)
        client_for(request).send(
            "agent.completed",
            payload={"outputs": create_outputs(request.workspace)},
        )
        session.finish(0)

    provider = FakeAgentProvider(behavior)
    runtime = AnimationGenerationOrchestrator(
        provider=provider,
        repo_root=repo_with_skill,
        workspace_root=tmp_path / "runs",
        processing_hook=processing_hook,
    )
    active = runtime.start(
        GenerationRequest("attack", "fake", tmp_path / "out", open_report=False)
    )
    return active, provider.requests[0], release


def envelope(request, event_type, *, event_id=None, sequence=10, iteration=None, payload=None):
    result = {
        "eventId": event_id or str(uuid.uuid4()),
        "runId": request.run_id,
        "sequence": sequence,
        "timestamp": "2026-09-11T00:00:00+00:00",
        "type": event_type,
        "payload": payload or {},
    }
    if iteration is not None:
        result["iteration"] = iteration
    return result


def test_post_returns_202_before_slow_processor(repo_with_skill, tmp_path):
    gate = threading.Event()

    def slow(event):
        if event.event_type == "agent.log":
            gate.wait(2)

    active, request, release = blocking_run(repo_with_skill, tmp_path, processing_hook=slow)
    started = time.monotonic()
    status, body = post_json(
        request.event_url,
        request.event_token,
        envelope(request, "agent.log", payload={"message": "queued"}),
    )
    elapsed = time.monotonic() - started
    assert status == 202
    assert body["accepted"] is True
    assert elapsed < 0.25
    assert not active.bus.queue.empty() or active.state.snapshot()["lastActivity"] is not None
    gate.set()
    release.set()
    active.wait()


def test_auth_run_id_dedupe_and_fifo_receive_order(repo_with_skill, tmp_path):
    active, request, release = blocking_run(repo_with_skill, tmp_path)
    event_id = str(uuid.uuid4())
    body = envelope(request, "agent.log", event_id=event_id, payload={"message": "once"})
    assert post_json(request.event_url, "wrong-token", body)[0] == 401
    wrong_run = dict(body, eventId=str(uuid.uuid4()), runId="wrong-run")
    assert post_json(request.event_url, request.event_token, wrong_run)[0] == 400
    assert post_json(request.event_url, request.event_token, body)[1]["duplicate"] is False
    assert post_json(request.event_url, request.event_token, body)[1]["duplicate"] is True
    active.processor.drain()
    events = active.store.snapshot()
    orders = [item["receiveOrder"] for item in events]
    assert orders == sorted(orders)
    assert sum(item["eventId"] == event_id for item in events) == 1
    assert next(item for item in events if item["eventId"] == event_id)["source"] == "agent_push"
    persisted = (active.workspace.logs / "events.jsonl").read_text(encoding="utf-8")
    assert persisted.count(event_id) == 1
    release.set()
    active.wait()


def test_skill_iteration_artifact_evidence_and_unknown_step_are_observations(
    repo_with_skill, tmp_path
):
    active, request, release = blocking_run(repo_with_skill, tmp_path)
    (request.workspace / "artifact.txt").write_text("artifact", encoding="utf-8")
    (request.workspace / "evidence.txt").write_text("evidence", encoding="utf-8")
    client = client_for(request)
    client.send("iteration.started", iteration=2, payload={"reason": "refine"})
    client.send(
        "skill.step.completed",
        iteration=2,
        payload={"step": "discover-references", "summary": "done"},
    )
    client.send(
        "skill.step.completed",
        iteration=2,
        payload={"step": "unknown-step", "summary": "reported"},
    )
    client.send("artifact.created", iteration=2, payload={"path": "artifact.txt"})
    client.send("evidence.created", iteration=2, payload={"path": "evidence.txt"})
    client.send("iteration.completed", iteration=2, payload={"summary": "done"})
    active.processor.drain()
    state = active.state.snapshot()
    assert state["skillSteps"]["2"]["discover-references"]["status"] == "completed"
    assert state["iterations"]["2"]["status"] == "completed"
    assert state["artifacts"][0]["name"] == "artifact.txt"
    assert state["evidence"][0]["name"] == "evidence.txt"
    assert any("unknown skill step" in item for item in state["warnings"])
    release.set()
    assert active.wait().status == "completed"


def test_heartbeat_and_sse_use_processed_event_store(repo_with_skill, tmp_path):
    active, request, release = blocking_run(repo_with_skill, tmp_path)
    client_for(request).send("agent.heartbeat")
    active.processor.drain()
    assert active.state.snapshot()["lastHeartbeat"] is not None
    with urllib.request.urlopen(active.report_url + "stream", timeout=2) as stream:
        data_line = b""
        for _ in range(20):
            line = stream.readline()
            if line.startswith(b"data:"):
                data_line = line
                break
        assert b'"source":"harness"' in data_line or b'"source":"agent_push"' in data_line
    release.set()
    active.wait()


def test_slow_sse_client_does_not_block_processor(repo_with_skill, tmp_path):
    active, request, release = blocking_run(repo_with_skill, tmp_path)
    stream = urllib.request.urlopen(active.report_url + "stream", timeout=2)
    started = time.monotonic()
    for index in range(20):
        client_for(request).send("agent.log", payload={"message": f"event {index}"})
    active.processor.drain()
    assert time.monotonic() - started < 1.5
    stream.close()
    release.set()
    active.wait()


def test_agent_and_provider_sequences_have_independent_provenance(repo_with_skill, tmp_path):
    active, request, release = blocking_run(repo_with_skill, tmp_path)
    client_for(request).send("agent.log", payload={"message": "push"})
    active.session.emit_provider(
        __import__(
            "motion2sheet.motion.harness_anim_generator.contracts", fromlist=["ProviderEvent"]
        ).ProviderEvent("command.completed", {"command": "opaque"}, raw={"sequence": 999})
    )
    deadline = time.monotonic() + 2
    while not any(item["source"] == "provider" for item in active.store.snapshot()) and time.monotonic() < deadline:
        time.sleep(0.01)
    events = active.store.snapshot()
    assert {item["source"] for item in events} >= {"agent_push", "provider", "harness"}
    assert all("sequence" not in item for item in events if item["source"] == "provider")
    orders = [item["receiveOrder"] for item in events]
    assert orders == sorted(orders)
    release.set()
    active.wait()


def test_liveness_transitions_reach_report_without_new_agent_events(repo_with_skill, tmp_path):
    release = threading.Event()

    def behavior(request, session):
        client_for(request).send("agent.started")
        release.wait(5)
        client_for(request).send(
            "agent.completed", payload={"outputs": create_outputs(request.workspace)}
        )
        session.finish(0)

    runtime = AnimationGenerationOrchestrator(
        provider=FakeAgentProvider(behavior),
        repo_root=repo_with_skill,
        workspace_root=tmp_path / "runs",
        liveness_idle_seconds=0.05,
        liveness_stalled_seconds=0.12,
        liveness_tick_seconds=0.01,
    )
    active = runtime.start(
        GenerationRequest("attack", "fake", tmp_path / "out", open_report=False)
    )

    observed = []
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        with urllib.request.urlopen(active.report_url + "snapshot", timeout=2) as response:
            snapshot = json.loads(response.read())["state"]
        alive = snapshot["agentAliveState"]
        if not observed or observed[-1] != alive:
            observed.append(alive)
        if alive == "possibly_stalled":
            break
        time.sleep(0.01)

    assert "idle" in observed
    assert observed[-1] == "possibly_stalled"
    liveness_events = [
        item for item in active.store.snapshot() if item["type"] == "runtime.liveness.changed"
    ]
    assert [item["payload"]["state"] for item in liveness_events] == [
        "idle",
        "possibly_stalled",
    ]
    assert all(item["source"] == "harness" for item in liveness_events)
    release.set()
    active.wait()
