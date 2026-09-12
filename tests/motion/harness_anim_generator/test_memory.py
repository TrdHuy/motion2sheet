from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import FakeAgentProvider, client_for, create_outputs
from motion2sheet.motion.harness_anim_generator.contracts import (
    GenerationRequest,
    HarnessError,
    MemorySecurityError,
    SkillManifest,
)
from motion2sheet.motion.harness_anim_generator.memory import (
    MAX_INJECTED_MEMORY_BYTES,
    MAX_INJECTED_MEMORY_ENTRIES,
    ProviderMemoryBank,
)
from motion2sheet.motion.harness_anim_generator.orchestrator import (
    AnimationGenerationOrchestrator,
)
from motion2sheet.motion.harness_anim_generator.providers.codex_cli import CodexCLIProvider


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


def completing_behavior(
    *, memory=None, proposal_path="memory-update.json", code=0, report_evidence=True
):
    def behavior(request, session):
        client = client_for(request)
        if memory is not None:
            if report_evidence:
                for entry in memory.get("entries", []):
                    for locator in entry.get("evidence", []):
                        base = locator.split("#", 1)[0]
                        evidence = request.workspace / base
                        evidence.parent.mkdir(parents=True, exist_ok=True)
                        evidence.write_bytes(b"evidence")
                        client.send("evidence.created", payload={"path": base})
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
        "archiveEntryCount": 0,
        "injectedEntryCount": 0,
        "truncated": False,
        "selectionPolicy": "newest-fit-first-chronological-output",
        "limits": {"maxEntries": 32, "maxBytes": 65536},
        "entries": [],
    }
    saved = json.loads((result.workspace / "request.json").read_text())
    assert saved["memory"] == provider.requests[0].memory
    state = json.loads((result.workspace / "run.json").read_text())
    assert state["memoryWorkingSet"]["archiveEntryCount"] == 0
    assert state["memoryWorkingSet"]["injectedEntryCount"] == 0
    assert state["memoryWorkingSet"]["truncated"] is False


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
        ("memory.loaded", "harness"),
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
    assert records[0]["entry"]["evidence"] == [
        "review/v2/pose-sheet.png#frame=12"
    ]


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


@pytest.mark.parametrize("mode", ["missing", "unreported"])
def test_missing_or_unreported_evidence_rejects_memory_but_keeps_output(
    repo_with_skill, tmp_path, mode
):
    memory = proposal(evidence=["review/evidence.png"])

    def behavior(request, session):
        if mode == "unreported":
            evidence = request.workspace / "review/evidence.png"
            evidence.parent.mkdir(parents=True)
            evidence.write_bytes(b"real but unreported")
        (request.workspace / "memory-update.json").write_text(
            json.dumps(memory), encoding="utf-8"
        )
        client = client_for(request)
        client.send("memory.proposed", payload={"path": "memory-update.json"})
        client.send("agent.completed", payload={"outputs": create_outputs(request.workspace)})
        session.finish(0)

    result = runtime(repo_with_skill, tmp_path, FakeAgentProvider(behavior)).run(
        run_request(tmp_path / "out")
    )
    state = json.loads((result.workspace / "run.json").read_text())
    assert state["status"] == "completed"
    assert state["memoryPersistence"]["status"] == "rejected"
    assert not (tmp_path / "memory").exists()
    assert (tmp_path / "out/animation.json").is_file()


def test_evidence_outside_workspace_is_security_failure(repo_with_skill, tmp_path):
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"outside")
    memory = proposal(evidence=["../outside.png"])

    def behavior(request, session):
        (request.workspace / "memory-update.json").write_text(
            json.dumps(memory), encoding="utf-8"
        )
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


def test_symlink_evidence_is_security_failure(repo_with_skill, tmp_path):
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"outside")
    memory = proposal(evidence=["review/evidence.png"])

    def behavior(request, session):
        evidence = request.workspace / "review/evidence.png"
        evidence.parent.mkdir(parents=True)
        evidence.symlink_to(outside)
        (request.workspace / "memory-update.json").write_text(
            json.dumps(memory), encoding="utf-8"
        )
        client = client_for(request)
        client.send("evidence.created", payload={"path": "review/evidence.png"})
        client.send("memory.proposed", payload={"path": "memory-update.json"})
        client.send("agent.completed", payload={"outputs": create_outputs(request.workspace)})
        session.finish(0)

    active = runtime(repo_with_skill, tmp_path, FakeAgentProvider(behavior)).start(
        run_request(tmp_path / "out")
    )
    with pytest.raises(MemorySecurityError, match="escapes agent workspace"):
        active.wait()
    assert not (tmp_path / "out").exists()


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
        evidence = request.workspace / "review/v2/pose-sheet.png"
        evidence.parent.mkdir(parents=True)
        evidence.write_bytes(b"evidence")
        (request.workspace / "memory-update.json").write_text(
            json.dumps(value), encoding="utf-8"
        )
        client = client_for(request)
        client.send(
            "evidence.created", payload={"path": "review/v2/pose-sheet.png"}
        )
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


def _archive_records(count: int, *, statement_size: int = 20) -> list[dict]:
    return [
        {
            "runId": f"run-{index}",
            "createdAt": f"2026-09-12T00:00:{index:02d}+00:00",
            "provider": "codex-cli",
            "skillId": "skill",
            "skillVersion": 3,
            "entryHash": f"{index:064x}",
            "entry": {
                "id": f"lesson-{index}",
                "kind": "learning",
                "statement": f"{index:03d}-" + ("x" * statement_size),
                "scope": ["test"],
                "references": [],
                "evidence": ["review/evidence.png"],
                "confidence": "high",
            },
        }
        for index in range(count)
    ]


def _seed_archive(
    bank: ProviderMemoryBank,
    records: list[dict],
    *,
    skill_id: str = "skill",
    provider: str = "codex-cli",
) -> Path:
    path = bank.path_for(skill_id, provider)
    path.parent.mkdir(parents=True)
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    return path


def test_small_archive_is_injected_in_full(tmp_path):
    bank = ProviderMemoryBank(tmp_path / "memory")
    records = _archive_records(3)
    _seed_archive(bank, records)
    payload = bank.load(SkillManifest("skill", 3, ()), "codex-cli")
    assert payload["entries"] == records
    assert payload["archiveEntryCount"] == payload["injectedEntryCount"] == 3
    assert payload["truncated"] is False


def test_large_archive_is_count_bounded_without_truncating_persistence(tmp_path):
    bank = ProviderMemoryBank(tmp_path / "memory")
    records = _archive_records(40)
    archive = _seed_archive(bank, records)
    before = archive.read_bytes()
    payload = bank.load(SkillManifest("skill", 3, ()), "codex-cli")
    assert payload["injectedEntryCount"] == MAX_INJECTED_MEMORY_ENTRIES
    assert [item["entry"]["id"] for item in payload["entries"]] == [
        f"lesson-{index}" for index in range(8, 40)
    ]
    assert payload["truncated"] is True
    assert archive.read_bytes() == before
    assert len(archive.read_text().splitlines()) == 40


def test_large_entries_are_byte_bounded_and_selection_is_deterministic(tmp_path):
    bank = ProviderMemoryBank(tmp_path / "memory")
    records = _archive_records(40, statement_size=4096)
    archive = _seed_archive(bank, records)
    first = bank.load(SkillManifest("skill", 3, ()), "codex-cli")
    second = bank.load(SkillManifest("skill", 3, ()), "codex-cli")
    assert first == second
    assert first["truncated"] is True
    assert first["injectedEntryCount"] < MAX_INJECTED_MEMORY_ENTRIES
    assert bank.serialized_size(first) <= MAX_INJECTED_MEMORY_BYTES
    assert len(archive.read_text().splitlines()) == 40


def test_codex_prompt_receives_only_bounded_working_memory(repo_with_skill, tmp_path):
    bank = ProviderMemoryBank(tmp_path / "memory")
    _seed_archive(
        bank,
        _archive_records(100, statement_size=4096),
        skill_id="humanoid-motion-local-authoring",
    )
    provider = FakeAgentProvider(completing_behavior())
    runtime(repo_with_skill, tmp_path, provider).run(run_request(tmp_path / "out"))
    request = provider.requests[0]
    encoded = json.dumps(
        request.memory,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert len(encoded.encode("utf-8")) <= MAX_INJECTED_MEMORY_BYTES
    assert request.memory["archiveEntryCount"] == 100
    assert request.memory["truncated"] is True
    assert encoded in CodexCLIProvider._prompt(request)
