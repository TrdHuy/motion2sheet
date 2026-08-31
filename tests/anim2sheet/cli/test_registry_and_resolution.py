from __future__ import annotations
from pathlib import Path
import json
import pytest
from motion2sheet.anim2sheet.cli import parser as cli_parser
from motion2sheet.anim2sheet.common.profile import resolve_review_request
from motion2sheet.anim2sheet.registry import get_authoring_capability
ROOT=Path(__file__).resolve().parents[3]; GALE=ROOT/"profiles/anim2sheet/animations/gale_slash/animation.json5"; IDLE=ROOT/"profiles/anim2sheet/animations/sword_idle/animation.json5"; CAMERAS=ROOT/"profiles/anim2sheet/cameras/fast_keypose_review.json"; CHAR=ROOT/"profiles/anim2sheet/characters/swordsman_v1.json5"
def resolve(profile:Path,*,frames=None,cameras=None,animation=None,character=None): return resolve_review_request(profile_path=profile,camera_profile_path=CAMERAS,frames=frames,cameras=cameras,animation=animation,character_profile_path=character)
def execution_argv(command:str,profile:Path=GALE): return [command,"--profile",str(profile),"--camera-profile",str(CAMERAS),"--output","build/test"]
def test_registry_resolves_authoring_capability_not_clip():
    definition=get_authoring_capability("humanoid_v2"); assert definition.capability=="humanoid_v2"; assert definition.blender_author=="common/authoring/humanoid.py"
def test_unknown_authoring_capability_fails():
    with pytest.raises(ValueError,match="Unsupported anim2sheet authoring capability"): get_authoring_capability("missing")
def test_gale_and_idle_resolve_same_generic_authoring_stack():
    gale=resolve(GALE); idle=resolve(IDLE); assert gale["animation"]=="gale_slash"; assert idle["animation"]=="sword_idle"; assert gale["authoringCapability"]==idle["authoringCapability"]=="humanoid_v2"; assert gale["rigProfilePath"]==idle["rigProfilePath"]; assert gale["characterProfilePath"]==idle["characterProfilePath"]; assert gale["source"]["generator"]==idle["source"]["generator"]=="profile-contract-v2"
def test_gale_review_without_frames_uses_motion_frames():
    request=resolve(GALE); assert request["executionFrames"]==list(range(1,17)); assert request["motionFrames"]==list(range(1,17))
def test_idle_review_uses_its_own_motion_frame_count():
    request=resolve(IDLE); assert request["executionFrames"]==[1,2,3,4]; assert request["motionFrames"]==[1,2,3,4]
def test_review_frame_subset_is_generic(): assert resolve(GALE,frames="7,8")["executionFrames"]==[7,8]; assert resolve(IDLE,frames="2,3")["executionFrames"]==[2,3]
def test_review_frame_outside_motion_fails_fast():
    with pytest.raises(ValueError,match="outside motion frames"): resolve(IDLE,frames="5")
def test_animation_flag_is_only_profile_action_assertion():
    assert resolve(IDLE,animation="sword_idle")["animation"]=="sword_idle"
    with pytest.raises(ValueError,match="does not match profile action"): resolve(IDLE,animation="gale_slash")
def test_default_and_compatible_character_override(): assert resolve(IDLE)["characterProfilePath"]==CHAR.resolve(); assert resolve(IDLE,character=CHAR)["characterProfilePath"]==CHAR.resolve()

def test_incompatible_character_override_fails_before_blender(tmp_path):
    rig=json.loads((ROOT/"profiles/anim2sheet/rigs/game_humanoid_v2.json5").read_text())
    rig["id"]="other_humanoid_v2"
    rig_path=tmp_path/"other_rig.json5"; rig_path.write_text(json.dumps(rig),encoding="utf-8")
    char=json.loads(CHAR.read_text()); char["id"]="other_swordsman_v1"; char["rigProfile"]=str(rig_path)
    char_path=tmp_path/"character.json5"; char_path.write_text(json.dumps(char),encoding="utf-8")
    parsed=cli_parser().parse_args([*execution_argv("review",IDLE),"--character-profile",str(char_path)])
    with pytest.raises(ValueError,match="motion rig / character rig mismatch"):
        resolve(IDLE,character=Path(parsed.character_profile))

def test_unknown_camera_fails_fast():
    with pytest.raises(ValueError,match="unknown cameras"): resolve(GALE,cameras="front_final,missing")
@pytest.mark.parametrize("command",["build","review"])
def test_cli_surface_removes_rig_and_joint_overrides(command):
    parsed=cli_parser().parse_args(execution_argv(command)); assert parsed.gif is False; assert parsed.animation is None; assert parsed.character_profile is None; assert not hasattr(parsed,"rig_profile"); assert not hasattr(parsed,"joint_contract")
    assert cli_parser().parse_args([*execution_argv(command),"--character-profile",str(CHAR),"--gif"]).gif is True
