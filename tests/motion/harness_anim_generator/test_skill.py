import json
from pathlib import Path

import pytest

from motion2sheet.motion.harness_anim_generator.contracts import SkillError
from motion2sheet.motion.harness_anim_generator.contracts import GenerationRequest
from motion2sheet.motion.harness_anim_generator.orchestrator import AnimationGenerationOrchestrator
from motion2sheet.motion.harness_anim_generator.skill import load_skill
from conftest import FakeAgentProvider, client_for, create_outputs


ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / "skills" / "humanoid-motion-local-authoring"


def test_committed_skill_and_observability_manifest_load():
    loaded = load_skill(SKILL)
    assert loaded.text == (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert loaded.manifest.id == "humanoid-motion-local-authoring"
    assert loaded.manifest.version == 3
    assert [step.id for step in loaded.manifest.steps] == [
        "understand-intent",
        "discover-references",
        "design-mechanics",
        "author-key-poses",
        "review-key-poses",
        "author-full-motion",
        "review-full-motion",
        "refine",
        "validate",
        "finalize",
    ]
    assert "### Provider Memory" in loaded.text
    assert "sdar-notify memory-update memory-update.json" in loaded.text
    assert (
        "current task evidence / current selected references > skill rules > provider memory"
        in loaded.text
    )


def test_committed_skill_uses_targeted_read_only_repository_context():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "chỉ current run agent workspace là write scope" in text
    assert "Không chạy\n`git status`, branch discovery, `git diff`" in text
    assert "repo-wide\n`grep`" in text
    assert "Không sửa repository và không ghi vào run cũ" in text


def test_full_committed_skill_is_passed_verbatim_to_provider(tmp_path):
    def behavior(request, session):
        client_for(request).send(
            "agent.completed", payload={"outputs": create_outputs(request.workspace)}
        )
        session.finish(0)

    provider = FakeAgentProvider(behavior)
    result = AnimationGenerationOrchestrator(
        provider=provider,
        repo_root=ROOT,
        workspace_root=tmp_path / "runs",
    ).run(GenerationRequest("prompt", "fake", tmp_path / "out", open_report=False))
    assert provider.requests[0].skill_text == (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert result.status == "completed"


def write_override_skill(directory: Path, *, manifest: str | None = None) -> str:
    directory.mkdir(parents=True)
    text = "# Override skill\n\nPerform only this supplied workflow.\n"
    (directory / "SKILL.md").write_text(text, encoding="utf-8")
    (directory / "skill.json").write_text(
        manifest
        or json.dumps(
            {
                "id": "sdar-test-override",
                "version": 1,
                "steps": [{"id": "finalize", "title": "Finalize supplied workflow"}],
            }
        ),
        encoding="utf-8",
    )
    return text


def test_request_skill_override_is_passed_and_persisted_with_resolved_provenance(tmp_path):
    override = tmp_path / "relative-parent" / "override-skill"
    expected_text = write_override_skill(override)

    def behavior(request, session):
        client_for(request).send(
            "agent.completed", payload={"outputs": create_outputs(request.workspace)}
        )
        session.finish(0)

    provider = FakeAgentProvider(behavior)
    result = AnimationGenerationOrchestrator(
        provider=provider,
        repo_root=ROOT,
        workspace_root=tmp_path / "runs",
    ).run(
        GenerationRequest(
            "prompt",
            "fake",
            tmp_path / "out",
            open_report=False,
            skill_directory=override,
        )
    )

    sent = provider.requests[0]
    assert sent.skill_text == expected_text
    assert sent.skill_manifest.id == "sdar-test-override"
    assert not hasattr(sent, "selected_reference")
    persisted = json.loads((result.workspace / "request.json").read_text(encoding="utf-8"))
    assert persisted["skill"] == str(override.resolve())
    assert persisted["skillManifest"] == {
        "id": "sdar-test-override",
        "version": 1,
        "steps": [{"id": "finalize", "title": "Finalize supplied workflow"}],
    }


@pytest.mark.parametrize("mode", ["missing", "malformed"])
def test_invalid_request_skill_override_fails_before_provider_launch(tmp_path, mode):
    override = tmp_path / "override-skill"
    if mode == "missing":
        override.mkdir()
    else:
        write_override_skill(override, manifest="{broken")
    provider = FakeAgentProvider(lambda _request, _session: None)
    runtime = AnimationGenerationOrchestrator(
        provider=provider,
        repo_root=ROOT,
        workspace_root=tmp_path / "runs",
    )
    with pytest.raises(SkillError, match="missing|cannot load"):
        runtime.start(
            GenerationRequest(
                "prompt",
                "fake",
                tmp_path / "out",
                open_report=False,
                skill_directory=override,
            )
        )
    assert provider.requests == []


def test_missing_or_malformed_skill_fails_closed(tmp_path):
    with pytest.raises(SkillError, match="missing"):
        load_skill(tmp_path)
    (tmp_path / "SKILL.md").write_text("real workflow", encoding="utf-8")
    (tmp_path / "skill.json").write_text("not-json", encoding="utf-8")
    with pytest.raises(SkillError, match="cannot load"):
        load_skill(tmp_path)
    (tmp_path / "skill.json").write_text(json.dumps({"id": "x"}), encoding="utf-8")
    with pytest.raises(SkillError, match="version"):
        load_skill(tmp_path)
