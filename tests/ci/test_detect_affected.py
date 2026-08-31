from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ci.detect_affected import load_manifest, resolve_targets


def resolve(*paths):
    return resolve_targets(load_manifest(), list(paths))


def test_component_change_runs_only_dependent_targets():
    components, targets = resolve("motion2sheet/motion/normalize/core.py")
    assert "motion-normalize" in components
    assert "motion-cli" in components
    assert "motion-normalize-unit" in targets
    assert "motion-synthetic-fbx" in targets
    assert "motion-synthetic-bvh" in targets
    assert "motion-mixamo-real" in targets
    assert "motion-output-mode-e2e" in targets
    assert "motion-retarget-unit" not in targets
    assert "vfx-unit" not in targets
    assert "vfx-splash-e2e" not in targets
    assert "anim-gale-slash-e2e" not in targets
    assert "sprite-workflow-contract" not in targets


def test_output_contract_change_runs_only_motion_dependents():
    components, targets = resolve("motion2sheet/motion/output/contracts.py")
    assert "motion-output" in components
    assert "motion-cli" in components
    assert "motion-output-unit" in targets
    assert "motion-output-mode-unit" in targets
    assert "motion-output-mode-e2e" in targets
    assert "motion-synthetic-fbx" in targets
    assert "motion-synthetic-bvh" in targets
    assert "motion-mixamo-real" in targets
    assert "vfx-unit" not in targets
    assert "vfx-splash-e2e" not in targets
    assert "anim-gale-slash-e2e" not in targets
    assert "sprite-workflow-contract" not in targets


def test_sprite_skill_change_runs_only_sprite_workflow_contract():
    components, targets = resolve("skills/pose-frame-to-sprite-frame/SKILL.md")
    assert components == {"sprite-workflow"}
    assert targets == {"sprite-workflow-contract"}


def test_sprite_sample_change_runs_only_sprite_workflow_contract():
    components, targets = resolve("sample/sprite-generation/walk-down/walk pose 4.png")
    assert components == {"sprite-workflow"}
    assert targets == {"sprite-workflow-contract"}


def test_vfx_effect_change_does_not_run_motion_or_anim():
    components, targets = resolve("motion2sheet/vfx2sheet/effects/splash/config.py")
    assert "vfx-splash" in components
    assert "vfx-unit" in targets
    assert "vfx-splash-e2e" in targets
    assert not any(name.startswith("motion-") for name in targets)
    assert not any(name.startswith("anim-") for name in targets)
    assert "sprite-workflow-contract" not in targets


def test_anim_common_change_runs_gale_slash_dependents():
    components, targets = resolve("motion2sheet/anim2sheet/common/camera/config.py")
    assert "anim-common" in components
    assert "anim-core" in components
    assert "anim-gale-slash" in components
    assert "anim-common-unit" in targets
    assert "anim-cli-unit" in targets
    assert "anim-gale-slash-unit" in targets
    assert "anim-gale-slash-e2e" in targets
    assert "vfx-splash-e2e" not in targets


def test_gale_slash_change_runs_only_relevant_anim_targets():
    components, targets = resolve("motion2sheet/anim2sheet/animations/gale_slash/contract.py")
    assert components == {"anim-gale-slash"}
    assert "anim-gale-slash-unit" in targets
    assert "anim-gale-slash-e2e" in targets
    assert "anim-common-unit" not in targets
    assert "vfx-splash-e2e" not in targets


def test_gale_slash_profile_change_runs_gale_slash_target():
    components, targets = resolve("profiles/anim2sheet/animations/gale_slash/joint_contract.json")
    assert components == {"anim-gale-slash"}
    assert "anim-gale-slash-e2e" in targets


def test_direct_mixamo_test_change_runs_only_mixamo_target():
    _, targets = resolve("tests/motion/e2e/verify_mixamo_output.py")
    assert targets == {"motion-mixamo-real"}


def test_direct_output_mode_unit_change_runs_only_output_mode_unit():
    _, targets = resolve("tests/motion/output/test_output_mode.py")
    assert targets == {"motion-output-mode-unit"}


def test_direct_output_mode_e2e_change_runs_only_output_mode_e2e():
    _, targets = resolve("tests/motion/e2e/verify_output_mode.py")
    assert targets == {"motion-output-mode-e2e"}


def test_direct_sprite_workflow_contract_change_runs_only_itself():
    _, targets = resolve("tests/sprite_workflow/test_single_frame_contract.py")
    assert targets == {"sprite-workflow-contract"}


def test_global_ci_change_runs_every_target():
    manifest = load_manifest()
    _, targets = resolve(".github/workflows/ci.yml")
    assert targets == set(manifest["test_targets"])


def test_unknown_path_fails_safe_to_full_ci():
    manifest = load_manifest()
    _, targets = resolve("motion2sheet/new_unmapped_module.py")
    assert targets == set(manifest["test_targets"])


def test_docs_only_change_runs_no_tests():
    _, targets = resolve("README.md", "docs/vfx2sheet.md", "docs/huong-dan-su-dung.md")
    assert targets == set()
