from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ci.detect_affected import discover_animation_clips, load_manifest, resolve_targets


def resolve(*paths, manifest=None):
    return resolve_targets(manifest or load_manifest(), list(paths))


def make_clip(repo_root: Path, name: str, *, unit: bool = False) -> None:
    clip_dir = repo_root / "profiles" / "anim2sheet" / "animations" / name
    clip_dir.mkdir(parents=True)
    for filename in ("animation.json5", "motion.json"):
        (clip_dir / filename).write_text("{}\n", encoding="utf-8")
    if unit:
        (repo_root / "tests" / "anim2sheet" / "animations" / name / "unit").mkdir(parents=True)


def anim_e2e_targets(manifest, targets):
    return {name for name in targets if manifest["test_targets"][name]["kind"] == "anim-e2e"}


def test_component_change_runs_only_dependent_targets():
    _, targets = resolve("motion2sheet/motion/normalize/core.py")
    assert "motion-normalize-unit" in targets
    assert "motion-synthetic-fbx" in targets
    assert "motion-humanoid-motion-unit" not in targets
    assert "vfx-unit" not in targets
    assert not anim_e2e_targets(load_manifest(), targets)


def test_vfx_effect_change_does_not_run_motion_or_anim():
    manifest = load_manifest()
    components, targets = resolve("motion2sheet/vfx2sheet/effects/splash/config.py", manifest=manifest)
    assert "vfx-splash" in components
    assert "vfx-unit" in targets
    assert "vfx-splash-e2e" in targets
    assert "motion-humanoid-motion-unit" not in targets
    assert not anim_e2e_targets(manifest, targets)


def test_dynamic_animation_discovery_accepts_v2_two_file_clip(tmp_path):
    make_clip(tmp_path, "walk")
    assert discover_animation_clips(tmp_path) == ["walk"]
    manifest = load_manifest(repo_root=tmp_path)
    assert manifest["test_targets"]["anim-walk-e2e"]["target"] == "walk"
    assert "anim-walk-unit" not in manifest["test_targets"]
    assert "anim-walk" not in manifest["components"]


def test_incomplete_animation_clip_fails_closed(tmp_path):
    clip = tmp_path / "profiles/anim2sheet/animations/walk"
    clip.mkdir(parents=True)
    (clip / "animation.json5").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Incomplete animation clip"):
        discover_animation_clips(tmp_path)


def test_unrelated_file_only_animation_directory_also_fails_closed(tmp_path):
    clip = tmp_path / "profiles/anim2sheet/animations/walk"
    clip.mkdir(parents=True)
    (clip / "README.md").write_text("wip\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Incomplete animation clip"):
        discover_animation_clips(tmp_path)


def test_dynamic_animation_discovery_adds_existing_unit_target(tmp_path):
    make_clip(tmp_path, "walk", unit=True)
    manifest = load_manifest(repo_root=tmp_path)
    assert manifest["test_targets"]["anim-walk-unit"]["path"] == "tests/anim2sheet/animations/walk/unit"


def test_synthetic_clip_only_change_selects_only_that_anim_e2e(tmp_path):
    make_clip(tmp_path, "walk")
    make_clip(tmp_path, "guard")
    manifest = load_manifest(repo_root=tmp_path)
    components, targets = resolve("profiles/anim2sheet/animations/walk/motion.json", manifest=manifest)
    assert components == set()
    assert anim_e2e_targets(manifest, targets) == {"anim-walk-e2e"}
    assert "anim-cli-unit" in targets


def test_common_change_selects_all_discovered_animation_clips(tmp_path):
    for clip in ("walk", "guard", "hurt"):
        make_clip(tmp_path, clip)
    manifest = load_manifest(repo_root=tmp_path)
    components, targets = resolve("motion2sheet/anim2sheet/common/profile.py", manifest=manifest)
    assert {"anim-common", "anim-core"}.issubset(components)
    assert anim_e2e_targets(manifest, targets) == {"anim-walk-e2e", "anim-guard-e2e", "anim-hurt-e2e"}


def test_full_ci_selects_all_discovered_animation_clips(tmp_path):
    for clip in ("walk", "guard", "hurt"):
        make_clip(tmp_path, clip)
    manifest = load_manifest(repo_root=tmp_path)
    _, targets = resolve_targets(manifest, [], full=True)
    assert anim_e2e_targets(manifest, targets) == {"anim-walk-e2e", "anim-guard-e2e", "anim-hurt-e2e"}


def test_main_ci_workflow_change_selects_only_routing_unit():
    manifest = load_manifest()
    components, targets = resolve(".github/workflows/ci.yml", manifest=manifest)
    assert components == set()
    assert targets == {"ci-affected-unit"}


def test_humanoid_workflow_is_owned_by_dedicated_ci_not_main_matrix():
    components, targets = resolve(".github/workflows/humanoid-motion.yml")
    assert components == set()
    assert targets == set()


def test_legacy_manual_workflow_changes_do_not_expand_main_ci():
    for path in (
        ".github/workflows/motion-roundtrip.yml",
        ".github/workflows/real-skin-cross-animation-e2e.yml",
        ".github/workflows/real-skin-e2e.yml",
        ".github/workflows/real-skin-preflight.yml",
        ".github/workflows/source-character-render.yml",
    ):
        components, targets = resolve(path)
        assert components == set(), path
        assert targets == set(), path


def test_current_repo_discovers_canonical_clips_without_manifest_whitelist():
    manifest = load_manifest()
    assert discover_animation_clips(ROOT) == ["gale_slash", "sword_idle"]
    assert "anim-gale-slash" not in manifest["components"]
    assert "anim-sword-idle" not in manifest["components"]


def test_gale_motion_change_does_not_pull_idle_e2e():
    manifest = load_manifest()
    _, targets = resolve("profiles/anim2sheet/animations/gale_slash/motion.json", manifest=manifest)
    assert anim_e2e_targets(manifest, targets) == {"anim-gale-slash-e2e"}
    assert "anim-gale-slash-unit" in targets
    assert "anim-sword-idle-unit" not in targets


def test_sword_idle_profile_change_does_not_pull_gale_e2e():
    manifest = load_manifest()
    _, targets = resolve("profiles/anim2sheet/animations/sword_idle/animation.json5", manifest=manifest)
    assert anim_e2e_targets(manifest, targets) == {"anim-sword-idle-e2e"}
    assert "anim-sword-idle-unit" in targets
    assert "anim-gale-slash-unit" not in targets


@pytest.mark.parametrize(
    "path",
    [
        "profiles/anim2sheet/cameras/fast_keypose_review.json",
        "profiles/anim2sheet/rigs/game_humanoid_v2.json5",
        "profiles/anim2sheet/characters/swordsman_v1.json5",
    ],
)
def test_anim_common_profile_change_runs_all_current_anim_e2e(path):
    manifest = load_manifest()
    _, targets = resolve(path, manifest=manifest)
    assert anim_e2e_targets(manifest, targets) == {"anim-gale-slash-e2e", "anim-sword-idle-e2e"}


def test_skin_change_selects_shared_and_humanoid_units_without_old_e2e():
    manifest = load_manifest()
    components, targets = resolve("motion2sheet/motion/skin/contract.py", manifest=manifest)
    assert {"motion-skin", "motion-model-render", "motion-humanoid-motion"}.issubset(components)
    assert "motion-skin-unit" in targets
    assert "motion-model-render-unit" in targets
    assert "motion-humanoid-motion-unit" in targets
    assert "motion-mixamo-real" not in targets
    assert not any(manifest["test_targets"][name]["kind"] == "motion-e2e" for name in targets)
    assert "vfx-splash-e2e" not in targets


def test_skin_test_change_selects_skin_unit():
    components, targets = resolve("tests/motion/skin/test_contract.py")
    assert components == set()
    assert targets == {"motion-skin-unit"}


def test_model_render_change_routes_shared_and_humanoid_units_only():
    manifest = load_manifest()
    components, targets = resolve("motion2sheet/motion/model_render/runner.py", manifest=manifest)
    assert {"motion-model-render", "motion-humanoid-motion"}.issubset(components)
    assert "motion-model-render-unit" in targets
    assert "motion-humanoid-motion-unit" in targets
    assert "motion-mixamo-real" not in targets
    assert not any(manifest["test_targets"][name]["kind"] == "motion-e2e" for name in targets)
    assert "vfx-splash-e2e" not in targets


def test_model_render_test_change_selects_only_model_render_unit():
    components, targets = resolve("tests/motion/model_render/test_runner.py")
    assert components == set()
    assert targets == {"motion-model-render-unit"}


def test_roundtrip_change_has_explicit_component_and_no_unrelated_fanout():
    manifest = load_manifest()
    components, targets = resolve("motion2sheet/motion/roundtrip/native_timing.py", manifest=manifest)
    assert "motion-roundtrip" in components
    assert "motion-humanoid-motion" in components
    assert "motion-roundtrip-unit" in targets
    assert "motion-humanoid-motion-unit" in targets
    assert not any(manifest["test_targets"][name]["kind"] == "motion-e2e" for name in targets)
    assert "vfx-unit" not in targets
    assert not anim_e2e_targets(manifest, targets)
    assert "sprite-workflow-contract" not in targets


def test_roundtrip_test_change_selects_roundtrip_unit_only():
    components, targets = resolve("tests/motion/roundtrip/test_contract.py")
    assert components == set()
    assert targets == {"motion-roundtrip-unit"}


def test_humanoid_motion_change_routes_only_its_unit_in_main_ci():
    manifest = load_manifest()
    components, targets = resolve("motion2sheet/motion/humanoid_motion/schema.py", manifest=manifest)
    assert components == {"motion-humanoid-motion"}
    assert targets == {"motion-humanoid-motion-unit"}
    assert not anim_e2e_targets(manifest, targets)


def test_humanoid_motion_profile_change_uses_humanoid_component():
    components, targets = resolve("profiles/humanoid_motion/mixamo_humanoid_v1.json")
    assert components == {"motion-humanoid-motion"}
    assert targets == {"motion-humanoid-motion-unit"}


def test_humanoid_motion_test_change_selects_only_humanoid_unit():
    components, targets = resolve("tests/motion/humanoid_motion/test_humanoid_motion.py")
    assert components == set()
    assert targets == {"motion-humanoid-motion-unit"}


def test_humanoid_ci_script_change_is_dedicated_workflow_only():
    components, targets = resolve("tests/motion/humanoid_motion/ci/run_smoke.sh")
    assert components == set()
    assert targets == set()


def test_motion_cli_change_selects_parser_unit_without_motion_e2e():
    manifest = load_manifest()
    components, targets = resolve("motion2sheet/motion/cli.py", manifest=manifest)
    assert components == {"motion-cli"}
    assert targets == {"motion-cli-unit"}
    assert not any(manifest["test_targets"][name]["kind"] == "motion-e2e" for name in targets)


def test_character_render_change_is_classified_without_humanoid_fanout():
    components, targets = resolve("motion2sheet/motion/character_render/runner.py")
    assert components == {"motion-character-render"}
    assert targets == {"motion-character-render-unit"}


def test_unknown_path_still_fails_safe_to_full_ci():
    manifest = load_manifest()
    _, targets = resolve("motion2sheet/new_unmapped_module.py", manifest=manifest)
    assert targets == set(manifest["test_targets"])


def test_docs_only_change_runs_no_tests():
    _, targets = resolve("README.md", "docs/vfx2sheet.md", "docs/huong-dan-su-dung.md")
    assert targets == set()
