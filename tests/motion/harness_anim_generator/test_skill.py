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
