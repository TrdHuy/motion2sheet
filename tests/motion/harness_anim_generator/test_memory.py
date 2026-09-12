from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import FakeAgentProvider, client_for, create_outputs
from motion2sheet.motion.harness_anim_generator.contracts import (
    GenerationRequest,
    HarnessError,
    MemorySecurityError,
)
from motion2sheet.motion.harness_anim_generator.orchestrator import (
    AnimationGenerationOrchestrator,
)


def runtime(repo: Path, tmp_path: Path, provider) -> AnimationGenerationOrchestrator:
    return AnimationGenerationOrchestrator(
        provider=provider,
        repo_root=repo,
        workspace_root=tmp_path / "runs",
        memory_root=tmp_path / "memory",
    )


def proposal(statement: str = "Reusable lesson", *, evidence=None) -> dict:
    return {
        "entries": [
            {
                "id": "lesson-1",
                "kind": "reference-learning",
                "statement": statement,
                "scope": ["heavy-attack"],
                "references": ["sample/humanoid_motion/mixamo/reference-x"],
                "evidence": evidence or ["review/v2/pose-sheet.png#frame=12"],
                "confidence": "high",
            }
        ]
    }


def completing_behavior(*, memory=None, proposal_path="memory-update.json", code=0):
    def behavior(request, session):
        client = client_for(request)
        if memory is not None:
            path = request.workspace / proposal_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(memory), encoding="utf-8")
            client.send("memory.proposed", payload={"path": proposal_path})
        client.send("agent.completed", payload={"outputs": create_outputs(request.workspace)})
        session.finish(code)

    return behavior


def run_request(output: Path, provider: str = "codex-cli", **kwargs) -> GenerationRequest:
    return GenerationRequest("create motion", provider, output, open_report=False, **kwargs)


def test_first_run_injects_empty_provider_memory(repo_with_skill, tmp_path):
    provider = FakeAgentProvider(completing_behavior())
    result = runtime(repo_with_skill, tmp_path, provider).run(
        run_request(tmp_path / "out")
    )

    assert provider.requests[0].memory == {
        "skillId": "humanoid-motion-local-authoring",
        "skillVersion": 1,
        "provider": "codex-cli",
        "entries": [],
    }
    saved = json.loads((result.workspace / "request.json").read_text())
    assert saved["memory"] == provider.requests[0].memory


def test_successful_run_persists_and_next_matching_run_loads_memory(
    repo_with_skill, tmp_path
):
    first_provider = FakeAgentProvider(completing_behavior(memory=proposal()))
    first = runtime(repo_with_skill, tmp_path, first_provider).run(
        run_request(tmp_path / "out-1")
    )
    state = json.loads((first.workspace / "run.json").read_text())
    assert state["memoryPersistence"]["status"] == "persisted"
    assert state["memoryPersistence"]["appended"] == 1
    events = [
        json.loads(line)
        for line in (first.workspace / "logs/events.jsonl").read_text().splitlines()
    ]
    memory_events = [item for item in events if item["type"].startswith("memory.")]
    assert [(item["type"], item["source"]) for item in memory_events] == [
        ("memory.proposed", "agent_push"),
        ("memory.persisted", "harness"),
    ]
    assert [item["receiveOrder"] for item in events] == sorted(
        item["receiveOrder"] for item in events
    )

    second_provider = FakeAgentProvider(completing_behavior())
    runtime(repo_with_skill, tmp_path, second_provider).run(
        run_request(tmp_path / "out-2")
    )
    records = second_provider.requests[0].memory["entries"]
    assert len(records) == 1
    assert records[0]["entry"]["statement"] == "Reusable lesson"
    assert records[0]["provider"] == "codex-cli"
    assert records[0]["runId"] == first.run_id


def test_memory_is_isolated_by_provider(repo_with_skill, tmp_path):
    runtime(
        repo_with_skill,
        tmp_path,
        FakeAgentProvider(completing_behavior(memory=proposal())),
    ).run(run_request(tmp_path / "out-1", "codex-cli"))

    other = FakeAgentProvider(completing_behavior())
    runtime(repo_with_skill, tmp_path, other).run(
        run_request(tmp_path / "out-2", "provider-b")
    )
    assert other.requests[0].memory["provider"] == "provider-b"
    assert other.requests[0].memory["entries"] == []


def test_memory_is_isolated_by_skill(repo_with_skill, tmp_path):
    runtime(
        repo_with_skill,
        tmp_path,
        FakeAgentProvider(completing_behavior(memory=proposal())),
    ).run(run_request(tmp_path / "out-1"))
    override = tmp_path / "other-skill"
    override.mkdir()
    (override / "SKILL.md").write_text("# Other\n", encoding="utf-8")
    (override / "skill.json").write_text(
        json.dumps(
            {
                "id": "other-skill",
                "version": 1,
                "steps": [{"id": "finalize", "title": "Finalize"}],
            }
        ),
        encoding="utf-8",
    )

    other = FakeAgentProvider(completing_behavior())
    runtime(repo_with_skill, tmp_path, other).run(
        run_request(tmp_path / "out-2", skill_directory=override)
    )
    assert other.requests[0].memory["skillId"] == "other-skill"
    assert other.requests[0].memory["entries"] == []


def test_no_memory_proposal_is_valid(repo_with_skill, tmp_path):
    provider = FakeAgentProvider(completing_behavior())
    result = runtime(repo_with_skill, tmp_path, provider).run(
        run_request(tmp_path / "out")
    )
    state = json.loads((result.workspace / "run.json").read_text())
    assert state["status"] == "completed"
    assert state["memoryProposal"] is None
    assert state["memoryPersistence"] is None
    assert not (tmp_path / "memory").exists()


def test_malformed_proposal_warns_without_corrupting_bank(repo_with_skill, tmp_path):
    runtime(
        repo_with_skill,
        tmp_path,
        FakeAgentProvider(completing_behavior(memory=proposal())),
    ).run(run_request(tmp_path / "seed-out"))
    bank = tmp_path / "memory/humanoid-motion-local-authoring/codex-cli/entries.jsonl"
    before = bank.read_bytes()
    behavior = completing_behavior(memory={"entries": [{"statement": "incomplete"}]})
    result = runtime(repo_with_skill, tmp_path, FakeAgentProvider(behavior)).run(
        run_request(tmp_path / "out")
    )
    state = json.loads((result.workspace / "run.json").read_text())
    assert state["status"] == "completed"
    assert state["memoryPersistence"]["status"] == "rejected"
    assert state["warnings"]
    assert bank.read_bytes() == before
    assert (tmp_path / "out/animation.json").is_file()


def test_exact_duplicate_is_not_appended_twice(repo_with_skill, tmp_path):
    for number in (1, 2):
        runtime(
            repo_with_skill,
            tmp_path,
            FakeAgentProvider(completing_behavior(memory=proposal())),
        ).run(run_request(tmp_path / f"out-{number}"))
    bank = tmp_path / "memory/humanoid-motion-local-authoring/codex-cli/entries.jsonl"
    lines = bank.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


@pytest.mark.parametrize("escape", ["../memory-update.json", "/tmp/memory-update.json"])
def test_memory_proposal_path_escape_fails_run(repo_with_skill, tmp_path, escape):
    def behavior(request, session):
        client = client_for(request)
        client.send("memory.proposed", payload={"path": escape})
        client.send("agent.completed", payload={"outputs": create_outputs(request.workspace)})
        session.finish(0)

    active = runtime(repo_with_skill, tmp_path, FakeAgentProvider(behavior)).start(
        run_request(tmp_path / "out")
    )
    with pytest.raises(MemorySecurityError, match="escapes agent workspace"):
        active.wait()
    assert not (tmp_path / "out").exists()


def test_memory_proposal_symlink_escape_fails_run(repo_with_skill, tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(proposal()), encoding="utf-8")

    def behavior(request, session):
        (request.workspace / "memory-update.json").symlink_to(outside)
        client = client_for(request)
        client.send("memory.proposed", payload={"path": "memory-update.json"})
        client.send("agent.completed", payload={"outputs": create_outputs(request.workspace)})
        session.finish(0)

    active = runtime(repo_with_skill, tmp_path, FakeAgentProvider(behavior)).start(
        run_request(tmp_path / "out")
    )
    with pytest.raises(MemorySecurityError, match="escapes agent workspace"):
        active.wait()
    assert not (tmp_path / "out").exists()


def test_memory_is_redacted_before_persistence(repo_with_skill, tmp_path):
    def behavior(request, session):
        value = proposal(f"Lesson accidentally echoed {request.event_token}")
        (request.workspace / "memory-update.json").write_text(
            json.dumps(value), encoding="utf-8"
        )
        client = client_for(request)
        client.send("memory.proposed", payload={"path": "memory-update.json"})
        client.send("agent.completed", payload={"outputs": create_outputs(request.workspace)})
        session.finish(0)

    provider = FakeAgentProvider(behavior)
    runtime(repo_with_skill, tmp_path, provider).run(run_request(tmp_path / "out"))
    token = provider.requests[0].event_token
    bank = tmp_path / "memory/humanoid-motion-local-authoring/codex-cli/entries.jsonl"
    persisted = bank.read_text(encoding="utf-8")
    assert token not in persisted
    assert "[REDACTED]" in persisted


def test_resume_history_and_provider_memory_are_independent_inputs(
    repo_with_skill, tmp_path
):
    first = runtime(
        repo_with_skill,
        tmp_path,
        FakeAgentProvider(completing_behavior(memory=proposal())),
    ).run(run_request(tmp_path / "out-1"))
    provider = FakeAgentProvider(completing_behavior())
    second = runtime(repo_with_skill, tmp_path, provider).run(
        run_request(tmp_path / "out-2", resume_run_id=first.run_id)
    )
    sent = provider.requests[0]
    assert sent.history["parentRunId"] == first.run_id
    assert sent.memory["entries"][0]["runId"] == first.run_id
    assert second.parent_run_id == first.run_id


def test_failed_process_does_not_promote_memory(repo_with_skill, tmp_path):
    active = runtime(
        repo_with_skill,
        tmp_path,
        FakeAgentProvider(completing_behavior(memory=proposal(), code=3)),
    ).start(run_request(tmp_path / "out"))
    with pytest.raises(HarnessError, match="exited with code 3"):
        active.wait()
    assert not (tmp_path / "memory").exists()
    assert not (tmp_path / "out").exists()
