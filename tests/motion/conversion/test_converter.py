from __future__ import annotations

import copy
import json
from pathlib import Path

import json5
import pytest

from motion2sheet.anim2sheet.common.profile import load_motion_profile, load_rig_profile, resolve_review_request
from motion2sheet.motion.conversion.converter import convert_animation_profile
from motion2sheet.motion.conversion.math3d import distance, inverse_affine, mul4, quat_from_matrix, rest_matrix, rotation4, translation4
from motion2sheet.motion.roundtrip.schema import validate_animation_document, validate_rig_document

REPO = Path(__file__).resolve().parents[3]
TARGET_RIG = REPO / "profiles/anim2sheet/rigs/game_humanoid_v2.json5"
CHARACTER = REPO / "profiles/anim2sheet/characters/swordsman_v1.json5"
MAPPING = REPO / "profiles/retarget/mixamo_to_game_humanoid_v2.json5"
CAMERA = REPO / "profiles/anim2sheet/cameras/fast_keypose_review.json"

SOURCE_GEOMETRY = {
    "mixamorig:Hips": ([0,0,0.96],[0,0,1.12]),
    "mixamorig:Spine": ([0,0,1.12],[0,0,1.25]),
    "mixamorig:Spine1": ([0,0,1.25],[0,0,1.40]),
    "mixamorig:Spine2": ([0,0,1.40],[0,0,1.56]),
    "mixamorig:Neck": ([0,0,1.56],[0,0,1.70]),
    "mixamorig:Head": ([0,0,1.70],[0,0,1.94]),
    "mixamorig:LeftShoulder": ([0,0,1.53],[-0.18,0,1.53]),
    "mixamorig:LeftArm": ([-0.18,0,1.53],[-0.48,0,1.42]),
    "mixamorig:LeftForeArm": ([-0.48,0,1.42],[-0.72,0,1.24]),
    "mixamorig:LeftHand": ([-0.72,0,1.24],[-0.82,0,1.17]),
    "mixamorig:RightShoulder": ([0,0,1.53],[0.18,0,1.53]),
    "mixamorig:RightArm": ([0.18,0,1.53],[0.48,0,1.42]),
    "mixamorig:RightForeArm": ([0.48,0,1.42],[0.72,0,1.24]),
    "mixamorig:RightHand": ([0.72,0,1.24],[0.82,0,1.17]),
    "mixamorig:LeftUpLeg": ([-0.17,0,0.96],[-0.23,0,0.56]),
    "mixamorig:LeftLeg": ([-0.23,0,0.56],[-0.30,0,0.14]),
    "mixamorig:LeftFoot": ([-0.30,0,0.14],[-0.30,-0.24,0.07]),
    "mixamorig:RightUpLeg": ([0.17,0,0.96],[0.23,0,0.56]),
    "mixamorig:RightLeg": ([0.23,0,0.56],[0.30,0,0.14]),
    "mixamorig:RightFoot": ([0.30,0,0.14],[0.30,-0.24,0.07]),
}
PARENTS = {
    "mixamorig:Hips": None,
    "mixamorig:Spine": "mixamorig:Hips",
    "mixamorig:Spine1": "mixamorig:Spine",
    "mixamorig:Spine2": "mixamorig:Spine1",
    "mixamorig:Neck": "mixamorig:Spine2",
    "mixamorig:Head": "mixamorig:Neck",
    "mixamorig:LeftShoulder": "mixamorig:Spine2",
    "mixamorig:LeftArm": "mixamorig:LeftShoulder",
    "mixamorig:LeftForeArm": "mixamorig:LeftArm",
    "mixamorig:LeftHand": "mixamorig:LeftForeArm",
    "mixamorig:RightShoulder": "mixamorig:Spine2",
    "mixamorig:RightArm": "mixamorig:RightShoulder",
    "mixamorig:RightForeArm": "mixamorig:RightArm",
    "mixamorig:RightHand": "mixamorig:RightForeArm",
    "mixamorig:LeftUpLeg": "mixamorig:Hips",
    "mixamorig:LeftLeg": "mixamorig:LeftUpLeg",
    "mixamorig:LeftFoot": "mixamorig:LeftLeg",
    "mixamorig:RightUpLeg": "mixamorig:Hips",
    "mixamorig:RightLeg": "mixamorig:RightUpLeg",
    "mixamorig:RightFoot": "mixamorig:RightLeg",
}


def _documents() -> tuple[dict, dict]:
    absolute = {name: rest_matrix(head, tail, 0.0) for name, (head, tail) in SOURCE_GEOMETRY.items()}
    bones = []
    for name, (head, tail) in SOURCE_GEOMETRY.items():
        parent = PARENTS[name]
        local = absolute[name] if parent is None else mul4(inverse_affine(absolute[parent]), absolute[name])
        bones.append({
            "name": name,
            "parent": parent,
            "rest": {"translation": list(translation4(local)), "rotationQuaternion": quat_from_matrix(rotation4(local)), "scale": [1.0,1.0,1.0]},
            "length": distance(tuple(head), tuple(tail)),
            "editGeometry": {"head": head, "tail": tail, "roll": 0.0},
            "properties": {
                "useConnect": False, "useDeform": True, "useInheritRotation": True,
                "useLocalLocation": True, "inheritScale": "FULL", "headRadius": 0.1,
                "tailRadius": 0.1, "envelopeDistance": 0.0, "envelopeWeight": 0.0,
            },
        })
    sha = "0" * 64
    rig = {
        "schema": "motion2sheet.source-rig", "version": 1, "id": "synthetic_mixamo",
        "source": {"format":"BVH","filename":"walk_mixamo.bvh","sha256":sha,"importer":"blender-bvh"},
        "coordinateSystem": {"space":"Blender scene after source import","handedness":"right-handed","rightAxis":"+X","forwardAxis":"-Y","upAxis":"+Z"},
        "units": {"system":"METRIC","metersPerBlenderUnit":1.0},
        "restAuthority":"editGeometry", "editGeometrySpace":"armature-local",
        "armatureObject": {"name":"Armature","dataName":"Armature","transform":{"translation":[0.0,0.0,0.0],"rotationQuaternion":[1.0,0.0,0.0,0.0],"scale":[1.0,1.0,1.0]}},
        "bones": bones,
    }
    identity = {"translation":[0.0,0.0,0.0],"rotationQuaternion":[1.0,0.0,0.0,0.0],"scale":[1.0,1.0,1.0]}
    frames = []
    for frame in (1,2):
        transforms = {name: copy.deepcopy(identity) for name in SOURCE_GEOMETRY}
        if frame == 2:
            transforms["mixamorig:Hips"]["translation"] = [0.02,-0.01,0.0]
        frames.append({"frame":frame,"bones":transforms})
    animation = {
        "schema":"motion2sheet.source-animation","version":1,"id":"synthetic_walk","rig":{"id":"synthetic_mixamo"},
        "source":{"format":"BVH","filename":"walk_mixamo.bvh","sha256":sha,"action":"Walk"},
        "fps":30.0,"fpsNumerator":30,"fpsBase":1.0,"frameRange":[1,2],"frameCount":2,
        "sampling":{"policy":"all-integer-source-frames-inclusive","step":1,"continuousSubframeBehaviorPreserved":False},
        "transformSpace":{"name":"blender-pose-matrix-basis","description":"Per-bone PoseBone.matrix_basis: pose-local delta relative to the bone rest basis, serialized as TRS."},
        "frames":frames,
    }
    validate_rig_document(rig)
    validate_animation_document(animation, rig)
    return rig, animation


def _write_contract_b(root: Path, rig: dict | None = None, animation: dict | None = None) -> tuple[Path,Path]:
    default_rig, default_animation = _documents()
    rig = default_rig if rig is None else rig
    animation = default_animation if animation is None else animation
    root.mkdir(parents=True, exist_ok=True)
    rig_path, animation_path = root / "rig.json", root / "animation.json"
    rig_path.write_text(json.dumps(rig, indent=2) + "\n", encoding="utf-8")
    animation_path.write_text(json.dumps(animation, indent=2) + "\n", encoding="utf-8")
    return rig_path, animation_path


def _convert(tmp_path: Path, *, output_name: str = "out", mapping: Path = MAPPING, target: Path = TARGET_RIG):
    rig_path, animation_path = _write_contract_b(tmp_path / "contract-b")
    output = tmp_path / output_name
    report = convert_animation_profile(
        source_rig_path=rig_path, source_animation_path=animation_path, target_rig_path=target,
        mapping_path=mapping, character_profile_path=CHARACTER, output=output,
    )
    return output, report


def test_deterministic_conversion_and_contract_a_loaders(tmp_path: Path):
    first, report = _convert(tmp_path, output_name="first")
    second, _ = _convert(tmp_path, output_name="second")
    for filename in ("motion.json","animation.json5","conversion.json"):
        assert (first / filename).read_bytes() == (second / filename).read_bytes()
    target = load_rig_profile(TARGET_RIG)
    motion = load_motion_profile(first / "motion.json", rig_profile=target)
    assert motion["fps"] == 30.0 and motion["frameCount"] == 2 and len(motion["frames"]) == 2
    resolved = resolve_review_request(profile_path=first / "animation.json5", camera_profile_path=CAMERA, frames=None, cameras="front_final")
    assert resolved["rigId"] == "game_humanoid_v2"
    assert resolved["animation"] == "walk_mixamo"
    assert report["sourceMotionFileRequired"] is False
    assert report["fidelity"]["pass"] is True


def test_left_right_never_swapped(tmp_path: Path):
    output, _ = _convert(tmp_path)
    motion = json.loads((output / "motion.json").read_text(encoding="utf-8"))
    for frame in motion["frames"]:
        assert frame["joints"]["leftElbow"][0] < frame["joints"]["rightElbow"][0]
        assert frame["joints"]["leftWrist"][0] < frame["joints"]["rightWrist"][0]
        assert frame["targets"]["leftAnkle"][0] < frame["targets"]["rightAnkle"][0]


def test_invalid_contract_b_rejected(tmp_path: Path):
    rig, animation = _documents()
    animation["schema"] = "not-contract-b"
    rig_path, animation_path = _write_contract_b(tmp_path / "bad", rig, animation)
    with pytest.raises(ValueError, match="unsupported animation schema"):
        convert_animation_profile(source_rig_path=rig_path, source_animation_path=animation_path, target_rig_path=TARGET_RIG, mapping_path=MAPPING, character_profile_path=CHARACTER, output=tmp_path / "out")


def test_missing_mapping_rejected(tmp_path: Path):
    mapping = json5.loads(MAPPING.read_text(encoding="utf-8"))
    mapping["bones"] = [row for row in mapping["bones"] if row["target"] != "LeftForeArm"]
    path = tmp_path / "missing.json5"
    path.write_text(json.dumps(mapping), encoding="utf-8")
    with pytest.raises(ValueError, match="required target mappings missing"):
        _convert(tmp_path, mapping=path)


def test_wrong_target_rig_rejected(tmp_path: Path):
    target = json5.loads(TARGET_RIG.read_text(encoding="utf-8"))
    target["id"] = "other_humanoid"
    path = tmp_path / "wrong_target.json5"
    path.write_text(json.dumps(target), encoding="utf-8")
    with pytest.raises(ValueError, match="mapping target rig mismatch"):
        _convert(tmp_path, target=path)


def test_no_source_motion_file_dependency_and_diagnostics(tmp_path: Path):
    assert not (tmp_path / "walk_mixamo.bvh").exists()
    output, report = _convert(tmp_path)
    assert (output / "conversion.json").is_file()
    assert report["sourceMotionFileRequired"] is False
    assert report["fidelity"]["worstSemantic"] in {"root","pelvis","head","leftElbow","leftWrist","rightElbow","rightWrist","leftKnee","leftAnkle","rightKnee","rightAnkle"}
    assert report["targetPoseFrames"]
    assert report["limitations"]
