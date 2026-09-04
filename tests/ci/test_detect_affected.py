from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from ci.detect_affected import discover_animation_clips, load_manifest, resolve_targets

def resolve(*paths,manifest=None): return resolve_targets(manifest or load_manifest(),list(paths))
def make_clip(repo_root:Path,name:str,*,unit:bool=False)->None:
    clip_dir=repo_root/"profiles"/"anim2sheet"/"animations"/name; clip_dir.mkdir(parents=True)
    for filename in ("animation.json5","motion.json"): (clip_dir/filename).write_text("{}\n",encoding="utf-8")
    if unit:(repo_root/"tests"/"anim2sheet"/"animations"/name/"unit").mkdir(parents=True)
def anim_e2e_targets(manifest,targets): return {name for name in targets if manifest["test_targets"][name]["kind"]=="anim-e2e"}
def test_component_change_runs_only_dependent_targets():
    _,targets=resolve("motion2sheet/motion/normalize/core.py"); assert "motion-normalize-unit" in targets; assert "motion-synthetic-fbx" in targets; assert "motion-contract-c-e2e" not in targets; assert "vfx-unit" not in targets; assert not any(name.endswith("-e2e") and name.startswith("anim-") for name in targets)
def test_vfx_effect_change_does_not_run_motion_or_anim():
    manifest=load_manifest(); components,targets=resolve("motion2sheet/vfx2sheet/effects/splash/config.py",manifest=manifest); assert "vfx-splash" in components; assert "vfx-unit" in targets; assert "vfx-splash-e2e" in targets; assert "motion-contract-c-e2e" not in targets; assert not anim_e2e_targets(manifest,targets)
def test_dynamic_animation_discovery_accepts_v2_two_file_clip(tmp_path):
    make_clip(tmp_path,"walk"); assert discover_animation_clips(tmp_path)==["walk"]; manifest=load_manifest(repo_root=tmp_path); assert manifest["test_targets"]["anim-walk-e2e"]["target"]=="walk"; assert "anim-walk-unit" not in manifest["test_targets"]; assert "anim-walk" not in manifest["components"]
def test_incomplete_animation_clip_fails_closed(tmp_path):
    clip=tmp_path/"profiles/anim2sheet/animations/walk"; clip.mkdir(parents=True); (clip/"animation.json5").write_text("{}\n",encoding="utf-8")
    with pytest.raises(ValueError,match="Incomplete animation clip"): discover_animation_clips(tmp_path)

def test_unrelated_file_only_animation_directory_also_fails_closed(tmp_path):
    clip=tmp_path/"profiles/anim2sheet/animations/walk"; clip.mkdir(parents=True); (clip/"README.md").write_text("wip\n",encoding="utf-8")
    with pytest.raises(ValueError,match="Incomplete animation clip"): discover_animation_clips(tmp_path)

def test_dynamic_animation_discovery_adds_existing_unit_target(tmp_path):
    make_clip(tmp_path,"walk",unit=True); manifest=load_manifest(repo_root=tmp_path); assert manifest["test_targets"]["anim-walk-unit"]["path"]=="tests/anim2sheet/animations/walk/unit"
def test_synthetic_clip_only_change_selects_only_that_anim_e2e(tmp_path):
    make_clip(tmp_path,"walk"); make_clip(tmp_path,"guard"); manifest=load_manifest(repo_root=tmp_path); components,targets=resolve("profiles/anim2sheet/animations/walk/motion.json",manifest=manifest); assert components==set(); assert anim_e2e_targets(manifest,targets)=={"anim-walk-e2e"}; assert "anim-cli-unit" in targets
def test_common_change_selects_all_discovered_animation_clips(tmp_path):
    for clip in ("walk","guard","hurt"):make_clip(tmp_path,clip)
    manifest=load_manifest(repo_root=tmp_path); components,targets=resolve("motion2sheet/anim2sheet/common/profile.py",manifest=manifest); assert {"anim-common","anim-core"}.issubset(components); assert anim_e2e_targets(manifest,targets)=={"anim-walk-e2e","anim-guard-e2e","anim-hurt-e2e"}
def test_full_ci_selects_all_discovered_animation_clips(tmp_path):
    for clip in ("walk","guard","hurt"):make_clip(tmp_path,clip)
    manifest=load_manifest(repo_root=tmp_path); _,targets=resolve_targets(manifest,[],full=True); assert anim_e2e_targets(manifest,targets)=={"anim-walk-e2e","anim-guard-e2e","anim-hurt-e2e"}
def test_global_ci_change_selects_all_discovered_animation_clips(tmp_path):
    for clip in ("walk","guard"):make_clip(tmp_path,clip)
    manifest=load_manifest(repo_root=tmp_path); _,targets=resolve(".github/workflows/ci.yml",manifest=manifest); assert targets==set(manifest["test_targets"]); assert anim_e2e_targets(manifest,targets)=={"anim-walk-e2e","anim-guard-e2e"}
def test_current_repo_discovers_canonical_clips_without_manifest_whitelist():
    manifest=load_manifest(); assert discover_animation_clips(ROOT)==["gale_slash","sword_idle"]; assert "anim-gale-slash" not in manifest["components"]; assert "anim-sword-idle" not in manifest["components"]
def test_gale_motion_change_does_not_pull_idle_e2e():
    manifest=load_manifest(); _,targets=resolve("profiles/anim2sheet/animations/gale_slash/motion.json",manifest=manifest); assert anim_e2e_targets(manifest,targets)=={"anim-gale-slash-e2e"}; assert "anim-gale-slash-unit" in targets; assert "anim-sword-idle-unit" not in targets
def test_sword_idle_profile_change_does_not_pull_gale_e2e():
    manifest=load_manifest(); _,targets=resolve("profiles/anim2sheet/animations/sword_idle/animation.json5",manifest=manifest); assert anim_e2e_targets(manifest,targets)=={"anim-sword-idle-e2e"}; assert "anim-sword-idle-unit" in targets; assert "anim-gale-slash-unit" not in targets
@pytest.mark.parametrize("path",["profiles/anim2sheet/cameras/fast_keypose_review.json","profiles/anim2sheet/rigs/game_humanoid_v2.json5","profiles/anim2sheet/characters/swordsman_v1.json5"])
def test_anim_common_profile_change_runs_all_current_anim_e2e(path):
    manifest=load_manifest(); _,targets=resolve(path,manifest=manifest); assert anim_e2e_targets(manifest,targets)=={"anim-gale-slash-e2e","anim-sword-idle-e2e"}
def test_skin_change_selects_skin_unit_without_unrelated_e2e():
    manifest=load_manifest(); components,targets=resolve("motion2sheet/motion/skin/contract.py",manifest=manifest); assert components=={"motion-skin","motion-model-render","motion-contract-c","motion-cli"}; assert "motion-skin-unit" in targets; assert "motion-model-render-unit" in targets; assert "motion-contract-c-unit" in targets; assert "motion-contract-c-e2e" in targets; assert "motion-mixamo-real" in targets; assert "vfx-splash-e2e" not in targets
def test_skin_test_change_selects_skin_unit():
    manifest=load_manifest(); components,targets=resolve("tests/motion/skin/test_contract.py",manifest=manifest); assert components==set(); assert targets=={"motion-skin-unit"}
def test_model_render_change_routes_unit_and_motion_cli_dependents():
    manifest=load_manifest(); components,targets=resolve("motion2sheet/motion/model_render/runner.py",manifest=manifest); assert {"motion-model-render","motion-contract-c","motion-cli"}.issubset(components); assert "motion-model-render-unit" in targets; assert "motion-contract-c-e2e" in targets; assert "motion-mixamo-real" in targets; assert "vfx-splash-e2e" not in targets
def test_model_render_test_change_selects_only_model_render_unit():
    manifest=load_manifest(); components,targets=resolve("tests/motion/model_render/test_runner.py",manifest=manifest); assert components==set(); assert targets=={"motion-model-render-unit"}
def test_contract_c_change_routes_its_unit_and_motion_cli_dependents_only():
    manifest=load_manifest(); components,targets=resolve("motion2sheet/motion/contract_c/schema.py",manifest=manifest)
    assert {"motion-contract-c","motion-cli"}.issubset(components)
    assert "motion-contract-c-unit" in targets
    assert "motion-contract-c-e2e" in targets
    assert "motion-synthetic-fbx" in targets and "motion-mixamo-real" in targets
    assert "vfx-unit" not in targets and not anim_e2e_targets(manifest,targets)
def test_contract_c_profile_change_uses_contract_c_component():
    manifest=load_manifest(); components,targets=resolve("profiles/contract_c/mixamo_humanoid_v1.json",manifest=manifest)
    assert "motion-contract-c" in components and "motion-contract-c-unit" in targets and "motion-contract-c-e2e" in targets
def test_contract_c_test_change_selects_only_contract_c_unit():
    manifest=load_manifest(); components,targets=resolve("tests/motion/contract_c/test_contract_c.py",manifest=manifest)
    assert components==set(); assert targets=={"motion-contract-c-unit"}
def test_contract_c_e2e_runner_change_selects_unit_and_e2e():
    manifest=load_manifest(); components,targets=resolve("tests/motion/contract_c/run_e2e.sh",manifest=manifest)
    assert components==set(); assert targets=={"motion-contract-c-unit","motion-contract-c-e2e"}
def test_motion_cli_change_selects_contract_c_e2e():
    manifest=load_manifest(); _,targets=resolve("motion2sheet/motion/cli.py",manifest=manifest)
    assert "motion-contract-c-e2e" in targets
def test_unknown_path_fails_safe_to_full_ci():
    manifest=load_manifest(); _,targets=resolve("motion2sheet/new_unmapped_module.py",manifest=manifest); assert targets==set(manifest["test_targets"])
def test_docs_only_change_runs_no_tests():
    _,targets=resolve("README.md","docs/vfx2sheet.md","docs/huong-dan-su-dung.md"); assert targets==set()
