from pathlib import Path

import pytest

from motion2sheet.motion.harness_anim_generator.contracts import GenerationRequest, HarnessError
from motion2sheet.motion.harness_anim_generator.orchestrator import AnimationGenerationOrchestrator


def test_nonempty_output_fails_before_any_component_runs(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    existing = output / "animation.json"
    existing.write_text("old", encoding="utf-8")
    orchestrator = AnimationGenerationOrchestrator(
        provider=None,
        references=None,
        adapter=None,
        reviewer=None,
        metadata_builder=None,
        workspace_root=tmp_path / "workspaces",
    )
    with pytest.raises(HarnessError, match="output must not exist"):
        orchestrator.run(GenerationRequest("attack", "fake", output))
    assert existing.read_text(encoding="utf-8") == "old"
    assert not (tmp_path / "workspaces").exists()


def test_humanoid_motion_has_no_reverse_harness_dependency():
    root = Path(__file__).resolve().parents[3]
    humanoid = root / "motion2sheet" / "motion" / "humanoid_motion"
    for path in humanoid.rglob("*.py"):
        assert "harness_anim_generator" not in path.read_text(encoding="utf-8"), path
