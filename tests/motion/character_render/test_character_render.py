from __future__ import annotations

import copy
from pathlib import Path

import pytest
from PIL import Image

from motion2sheet.motion.character_render.diagnostics import frame_bounds
from motion2sheet.motion.character_render.profile import validate_character_compatibility
from motion2sheet.motion.character_render.runner import _compose_gif, gif_frame_durations_ms, parse_frames
from motion2sheet.motion.cli import parser


def _source_rig():
    def bone(name,parent,head,tail,roll=0.0): return {"name":name,"parent":parent,"editGeometry":{"head":head,"tail":tail,"roll":roll}}
    return {"coordinateSystem":{"handedness":"right-handed","rightAxis":"+X","forwardAxis":"-Y","upAxis":"+Z"},"bones":[bone("mixamorig:Hips",None,[0,0,0],[0,1,0]),bone("mixamorig:HeadTop_End","mixamorig:Hips",[0,1,0],[0,2,0]),bone("mixamorig:LeftArm","mixamorig:Hips",[0,1,0],[-1,1,0],1.2),bone("mixamorig:RightArm","mixamorig:Hips",[0,1,0],[1,1,0],-1.2)]}

def _character():
    s=_source_rig(); return {"rig":{"canonicalRig":"mixamo-compatible-v1","coordinateSystem":copy.deepcopy(s["coordinateSystem"]),"bones":[{"name":b["name"],"parent":b["parent"],"head":copy.deepcopy(b["editGeometry"]["head"]),"tail":copy.deepcopy(b["editGeometry"]["tail"]),"roll":b["editGeometry"]["roll"]} for b in s["bones"]],"rootMotion":{"bone":"mixamorig:Hips","policy":"scale-by-stature"},"nonRootTranslation":{"policy":"scale-by-bone-length"},"compatibility":{"restOrientationToleranceDegrees":0.001}}}

def test_same_topology_different_bone_lengths_is_compatible():
    source=_source_rig(); char=_character(); row=next(x for x in char["rig"]["bones"] if x["name"]=="mixamorig:LeftArm"); row["tail"]=[-1.5,1,0]
    result=validate_character_compatibility(source,char)
    assert result["pass"] is True
    assert result["translationScales"]["mixamorig:LeftArm"] == pytest.approx(1.5)

def test_missing_bone_fails_closed():
    char=_character(); char["rig"]["bones"].pop()
    with pytest.raises(ValueError,match="bone set incompatible"): validate_character_compatibility(_source_rig(),char)

def test_parent_topology_change_fails_closed():
    char=_character(); next(x for x in char["rig"]["bones"] if x["name"]=="mixamorig:LeftArm")["parent"]="mixamorig:HeadTop_End"
    with pytest.raises(ValueError,match="parent topology incompatible"): validate_character_compatibility(_source_rig(),char)

def test_rest_orientation_change_fails_closed():
    char=_character(); row=next(x for x in char["rig"]["bones"] if x["name"]=="mixamorig:LeftArm"); row["tail"]=[0,1,1]
    with pytest.raises(ValueError,match="rest orientation incompatible"): validate_character_compatibility(_source_rig(),char)

def test_frames_preserve_source_order_and_validate_selection():
    animation={"frames":[{"frame":1},{"frame":2},{"frame":3}]}
    assert parse_frames("all",animation)==[1,2,3]
    assert parse_frames("1,3",animation)==[1,3]
    with pytest.raises(ValueError,match="outside Contract B"): parse_frames("4",animation)

def test_diagnostics_frame_bounds_are_scalar_first_and_last():
    first,last=frame_bounds({1:"frame1",32:"frame32"})
    assert first==1
    assert last==32
    assert not isinstance(first,tuple)
    assert not isinstance(last,tuple)

def test_gif_timing_preserves_30fps_average_for_32_frames(tmp_path: Path):
    durations=gif_frame_durations_ms(32,30.0)
    assert len(durations)==32
    assert set(durations)=={30,40}
    assert sum(durations)==1070
    assert sum(durations)!=960
    assert sum(durations)==pytest.approx(32/30.0*1000.0,abs=5.0)

    frames=[]
    for index in range(32):
        path=tmp_path/f"frame_{index:04d}.png"
        Image.new("RGBA",(8,8),(index%255,0,0,255)).save(path)
        frames.append(path)
    report=_compose_gif(frames,tmp_path/"preview.gif",30.0)
    assert report["totalDurationMs"]==1070
    assert report["effectiveFps"]==pytest.approx(32*1000/1070)
    with Image.open(tmp_path/"preview.gif") as image:
        assert image.n_frames==32
        encoded=[]
        for frame in range(image.n_frames):
            image.seek(frame)
            encoded.append(int(image.info["duration"]))
    assert sum(encoded)==1070
    assert sum(encoded)!=960

def test_public_command_belongs_to_motion2sheet():
    args=parser().parse_args(["render-character-animation","--rig","r.json","--animation","a.json","--character-profile","c.json5","--camera-profile","cam.json5","--output","out"])
    assert args.command=="render-character-animation"

def test_new_path_has_no_anim2sheet_dependency():
    root=Path(__file__).resolve().parents[3]/"motion2sheet/motion/character_render"
    for path in root.glob("*.py"):
        assert "motion2sheet.anim2sheet" not in path.read_text(encoding="utf-8")
