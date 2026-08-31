from __future__ import annotations
import copy, json
from pathlib import Path
import pytest
from motion2sheet.anim2sheet.common.profile import (
    load_animation_profile, load_motion_profile, load_rig_profile,
    resolve_character_profile, resolve_motion_profile, resolve_review_request,
)
ROOT=Path(__file__).resolve().parents[3]
RIG=ROOT/"profiles/anim2sheet/rigs/game_humanoid_v2.json5"
CHAR=ROOT/"profiles/anim2sheet/characters/swordsman_v1.json5"
CAM=ROOT/"profiles/anim2sheet/cameras/fast_keypose_review.json"
GALE=ROOT/"profiles/anim2sheet/animations/gale_slash/animation.json5"
IDLE=ROOT/"profiles/anim2sheet/animations/sword_idle/animation.json5"

def resolve(path=GALE,**kwargs): return resolve_review_request(profile_path=path,camera_profile_path=CAM,frames=None,cameras=None,**kwargs)
def write_json(path,data): path.write_text(json.dumps(data,indent=2)+"\n",encoding="utf-8"); return path

def test_rig_profile_v2_owns_mechanics_and_motion_channel_contract():
    rig=load_rig_profile(RIG); assert (rig["schema"],rig["version"],rig["id"])==("anim2sheet.rig",2,"game_humanoid_v2"); assert rig["authoringCapability"]=="humanoid_v2"; assert rig["solvers"]["legs"]["sides"]["left"]["poleAngleDeg"]==0; assert rig["solvers"]["legs"]["sides"]["right"]["poleAngleDeg"]==180; assert rig["motionContract"]["rootTranslation"]=={"type":"vec3","required":True}
def test_character_resolves_explicit_rig_profile():
    result=resolve_character_profile(CHAR); assert result["profile"]["id"]=="swordsman_v1"; assert result["profile"]["rigProfile"]=="../rigs/game_humanoid_v2.json5"; assert result["rigProfile"]["id"]=="game_humanoid_v2"
def test_motion_resolves_explicit_target_rig_profile():
    result=resolve_motion_profile(ROOT/"profiles/anim2sheet/animations/gale_slash/motion.json"); assert result["profile"]["id"]=="gale_slash_v1"; assert result["rigProfile"]["id"]=="game_humanoid_v2"
def test_animation_resolves_motion_and_default_character_to_same_rig():
    value=resolve(); assert value["profile"]["id"]=="gale_slash_v1"; assert value["profile"]["motionProfile"]=="motion.json"; assert value["characterProfile"]["id"]=="swordsman_v1"; assert value["motionProfile"]["rigProfile"]=="../../rigs/game_humanoid_v2.json5"; assert value["rigProfile"]["id"]=="game_humanoid_v2"; assert value["source"]["generator"]=="profile-contract-v2"


def test_animation_requires_stable_id(tmp_path):
    data=load_animation_profile(GALE).copy(); data.pop("id")
    path=write_json(tmp_path/"animation.json5",data)
    with pytest.raises(ValueError,match="animation profile id"): load_animation_profile(path)

def test_rig_deterministic_arm_fk_has_no_legacy_arm_ik_targets_or_chains():
    rig=load_rig_profile(RIG)
    semantics={row["semantic"] for row in rig["targets"]}
    assert semantics=={"leftAnkle","rightAnkle","leftKneeGuide","rightKneeGuide"}
    assert all(row["target"] in {"leftAnkle","rightAnkle"} for row in rig["solvers"]["ikChains"])
    assert all("ikConstraint" not in cfg for cfg in rig["solvers"]["arms"]["sides"].values())

def test_legacy_canonical_motion_files_are_deleted():
    for clip in ("gale_slash","sword_idle"):
        root=ROOT/f"profiles/anim2sheet/animations/{clip}"
        assert not (root/"pose_reference.json").exists()
        assert not (root/"joint_contract.json").exists()

def test_motion_character_rig_mismatch_fails(tmp_path):
    alt=copy.deepcopy(load_rig_profile(RIG)); alt["id"]="other_humanoid_v2"; alt_path=write_json(tmp_path/"other.json5",alt)
    character=json.loads(json.dumps(resolve_character_profile(CHAR)["profile"])); character["rigProfile"]=str(alt_path); char_path=write_json(tmp_path/"char.json5",character)
    with pytest.raises(ValueError,match="motion rig / character rig mismatch"): resolve(character_profile_path=char_path)
def test_motion_frame_is_single_final_effective_state():
    motion=resolve()["motionProfile"]; frame=motion["frames"][6]; assert set(frame)=={"frame","root","body","joints","targets"}; assert set(frame["root"])=={"translation"}; assert len(frame["root"]["translation"])==3
@pytest.mark.parametrize("legacy",["poseReference","jointContract","rootOverride","bodyOverride","legOverride"])
def test_canonical_runtime_and_profiles_have_no_legacy_dual_authority_tokens(legacy):
    roots=[ROOT/"motion2sheet/anim2sheet",ROOT/"profiles/anim2sheet"]
    violations=[]
    for base in roots:
        for path in base.rglob("*"):
            if path.is_file() and path.suffix in {".py",".json",".json5"} and legacy in path.read_text(encoding="utf-8"):
                violations.append(str(path.relative_to(ROOT)))
    assert not violations,f"legacy motion-authority token {legacy!r} remains: {violations}"
def test_unknown_motion_semantic_fails_closed(tmp_path):
    rig=load_rig_profile(RIG); motion=copy.deepcopy(resolve()["motionProfile"]); motion["frames"][0]["joints"]["mysteryJoint"]=[0,0,0]; path=write_json(tmp_path/"motion.json",motion)
    with pytest.raises(ValueError,match="unknown=.*mysteryJoint"): load_motion_profile(path,rig_profile=rig)
def test_malformed_xyz_fails(tmp_path):
    rig=load_rig_profile(RIG); motion=copy.deepcopy(resolve()["motionProfile"]); motion["frames"][0]["root"]["translation"]=[0,1]; path=write_json(tmp_path/"motion.json",motion)
    with pytest.raises(ValueError,match="3-number array"): load_motion_profile(path,rig_profile=rig)
def test_non_contiguous_frames_fail(tmp_path):
    rig=load_rig_profile(RIG); motion=copy.deepcopy(resolve()["motionProfile"]); motion["frames"][1]["frame"]=3; path=write_json(tmp_path/"motion.json",motion)
    with pytest.raises(ValueError,match="ordered, unique and contiguous"): load_motion_profile(path,rig_profile=rig)
def test_migrated_motion_matches_frozen_v1_effective_state_digest():
    import hashlib
    expected={
        "gale_slash":"06caaf45199f4a16deeb9073cae34f44bd433167916ec387bb45559b6d26765e",
        "sword_idle":"cb83a5d81dfd4cded701004864314b0c59b4e664049ecc98175766e5182072d6",
    }
    for clip,digest in expected.items():
        motion=json.loads((ROOT/f"profiles/anim2sheet/animations/{clip}/motion.json").read_text())
        payload=json.dumps(motion["frames"],sort_keys=True,separators=(",",":"))
        assert hashlib.sha256(payload.encode()).hexdigest()==digest

def test_default_character_and_compatible_override():
    base=resolve(IDLE); overridden=resolve(IDLE,character_profile_path=CHAR); assert base["characterProfilePath"]==CHAR.resolve(); assert overridden["characterProfilePath"]==CHAR.resolve()
def test_animation_profile_contains_no_motion_owned_fields():
    for path in (GALE,IDLE):
        data=load_animation_profile(path); assert not ({"rigProfile","fps","frameCount","frames"}&set(data)); assert set(data)>= {"motionProfile","defaultCharacterProfile","render"}
