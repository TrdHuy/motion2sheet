from __future__ import annotations

import copy
import inspect
import json
import re
from pathlib import Path

import pytest

from motion2sheet.motion.cli import parser
from motion2sheet.motion.humanoid_motion.fidelity import compare_source_to_humanoid_motion
from motion2sheet.motion.humanoid_motion.mapping import mapping_diagnostics, validate_character_mapping
from motion2sheet.motion.humanoid_motion.root_motion import humanoid_root_motion
from motion2sheet.motion.humanoid_motion.runner import parse_samples
from motion2sheet.motion.humanoid_motion.schema import (
    ANIMATION_SCHEMA,
    CANONICAL_SKELETON,
    EXPECTED_COORDINATE_SYSTEM,
    EXPECTED_QUATERNION_CONVENTION,
    MAPPED_JOINTS,
    ROTATION_JOINTS,
    ROOT_TRANSLATION_TOLERANCE,
    validate_animation,
)


def _animation(frame_count=2):
    identity = [1.0, 0.0, 0.0, 0.0]
    return {
        "schema": ANIMATION_SCHEMA,
        "version": 1,
        "id": "run",
        "canonicalSkeleton": "humanoid_v1",
        "durationSeconds": (frame_count - 1) / 30.0,
        "fps": 30.0,
        "frameCount": frame_count,
        "loop": True,
        "coordinateSystem": copy.deepcopy(EXPECTED_COORDINATE_SYSTEM),
        "quaternionConvention": copy.deepcopy(EXPECTED_QUATERNION_CONVENTION),
        "root": {
            "translations": [[0.0, 0.0, 0.0] for _index in range(frame_count)],
            "rotations": [identity[:] for _ in range(frame_count)],
        },
        "hips": {
            "translations": [],
            "rotations": [identity[:] for _ in range(frame_count)],
        },
        "joints": {
            semantic: {"rotations": [identity[:] for _ in range(frame_count)]}
            for semantic in ROTATION_JOINTS
        },
    }


def _properties():
    return {
        "useConnect": False,
        "useDeform": True,
        "useInheritRotation": True,
        "useLocalLocation": True,
        "inheritScale": "FULL",
        "headRadius": 0.1,
        "tailRadius": 0.1,
        "envelopeDistance": 0.0,
        "envelopeWeight": 1.0,
        "useRelativeParent": False,
    }


def _rig_and_mapping():
    bones = []
    heads = {}
    joints = {}
    for semantic in MAPPED_JOINTS:
        parent_semantic = CANONICAL_SKELETON[semantic]
        parent_name = joints.get(parent_semantic)
        side_x = 1.0 if semantic.startswith("Left") else -1.0 if semantic.startswith("Right") else 0.0
        head = [0.0, 0.0, 0.0] if parent_name is None else [side_x, heads[parent_name][1] + 1.0, 0.0]
        name = f"bone_{semantic}"
        joints[semantic] = name
        heads[name] = head
        parent_head = heads[parent_name] if parent_name else [0.0, 0.0, 0.0]
        translation = head if parent_name is None else [head[index] - parent_head[index] for index in range(3)]
        bones.append({
            "name": name,
            "parent": parent_name,
            "rest": {"translation": translation, "rotationQuaternion": [1.0, 0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0]},
            "length": 1.0,
            "editGeometry": {"head": head, "tail": [head[0], head[1] + 1.0, head[2]], "roll": 0.0},
            "properties": _properties(),
        })
    rig = {
        "schema": "motion2sheet.source-rig",
        "version": 1,
        "id": "humanoid-motion-fixture-rig",
        "source": {"format": "BVH", "filename": "fixture.bvh", "sha256": "0" * 64, "importer": "blender-bvh"},
        "coordinateSystem": {"space": "Blender scene after source import", "handedness": "right-handed", "rightAxis": "+X", "forwardAxis": "-Y", "upAxis": "+Z"},
        "units": {"system": "NONE", "metersPerBlenderUnit": 1.0},
        "restAuthority": "editGeometry",
        "editGeometrySpace": "armature-local",
        "armatureObject": {"name": "Armature", "dataName": "Armature", "transform": {"translation": [0.0, 0.0, 0.0], "rotationQuaternion": [1.0, 0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0]}},
        "bones": bones,
    }
    mapping = {"schema": "motion2sheet.humanoid-motion.character-map", "version": 1, "id": "fixture", "canonicalSkeleton": "humanoid_v1", "joints": joints}
    return rig, mapping


def test_public_cli_exposes_humanoid_motion_commands():
    root = parser()
    export = root.parse_args(["export-humanoid-animation", "--source-rig", "rig.json", "--source-animation", "animation.json", "--mapping", "map.json", "--id", "run", "--output", "out"])
    assert export.command == "export-humanoid-animation"
    render = root.parse_args(["render-humanoid-animation", "--model", "model.glb", "--character-rig", "rig.json", "--skin", "skin.json", "--character-mapping", "map.json", "--animation", "animation.json", "--camera-profile", "camera.json5", "--output", "out"])
    assert render.command == "render-humanoid-animation"
    fidelity = root.parse_args(["verify-humanoid-animation-fidelity", "--source-rig", "rig.json", "--source-animation", "source.json", "--source-mapping", "map.json", "--animation", "animation.json", "--output", "report.json"])
    assert fidelity.command == "verify-humanoid-animation-fidelity"


def test_humanoid_motion_schema_is_strict_and_complete():
    assert validate_animation(_animation())["frameCount"] == 2
    missing = _animation()
    del missing["joints"]["LeftUpperArm"]
    with pytest.raises(ValueError, match="joint set mismatch"):
        validate_animation(missing)
    world_positions = _animation()
    world_positions["joints"]["Head"]["worldPositions"] = [[0, 0, 0], [0, 0, 0]]
    with pytest.raises(ValueError, match="unknown fields"):
        validate_animation(world_positions)
    moving_root = _animation(3)
    moving_root["root"]["translations"][1] = [0.0, ROOT_TRANSLATION_TOLERANCE * 2.0, 0.0]
    with pytest.raises(ValueError, match="must be in-place"):
        validate_animation(moving_root)
    tolerated_root = _animation()
    tolerated_root["root"]["translations"][1] = [ROOT_TRANSLATION_TOLERANCE, 0.0, 0.0]
    assert validate_animation(tolerated_root)["root"]["translations"][1][0] == ROOT_TRANSLATION_TOLERANCE
    missing_duration = _animation()
    del missing_duration["durationSeconds"]
    with pytest.raises(ValueError, match="missing fields.*durationSeconds"):
        validate_animation(missing_duration)
    wrong_duration = _animation()
    wrong_duration["durationSeconds"] += 0.01
    with pytest.raises(ValueError, match="durationSeconds contradicts"):
        validate_animation(wrong_duration)


def test_quaternion_normalization_and_sign_continuity_fail_closed():
    invalid = _animation()
    invalid["joints"]["Head"]["rotations"][0] = [2.0, 0.0, 0.0, 0.0]
    with pytest.raises(ValueError, match="normalized"):
        validate_animation(invalid)
    discontinuous = _animation()
    discontinuous["joints"]["Head"]["rotations"][1] = [-1.0, 0.0, 0.0, 0.0]
    with pytest.raises(ValueError, match="sign-continuous"):
        validate_animation(discontinuous)


def test_mapping_requires_every_semantic_and_valid_ancestry():
    rig, mapping = _rig_and_mapping()
    assert validate_character_mapping(mapping, rig) is mapping
    assert mapping_diagnostics(mapping, rig)["mappedJointCount"] == 21
    missing = copy.deepcopy(mapping)
    del missing["joints"]["LeftToe"]
    with pytest.raises(ValueError, match="semantic set mismatch"):
        validate_character_mapping(missing, rig)
    wrong = copy.deepcopy(mapping)
    wrong["joints"]["Head"], wrong["joints"]["LeftHand"] = wrong["joints"]["LeftHand"], wrong["joints"]["Head"]
    with pytest.raises(ValueError, match="hierarchy mismatch"):
        validate_character_mapping(wrong, rig)
    swapped = copy.deepcopy(mapping)
    for suffix in ("Shoulder", "UpperArm", "LowerArm", "Hand", "UpperLeg", "LowerLeg", "Foot", "Toe"):
        left, right = f"Left{suffix}", f"Right{suffix}"
        swapped["joints"][left], swapped["joints"][right] = swapped["joints"][right], swapped["joints"][left]
    with pytest.raises(ValueError, match="left/right geometry mismatch"):
        validate_character_mapping(swapped, rig)


def test_root_motion_checks_every_sample_and_sample_selection_is_data_driven():
    animation = _animation(3)
    animation["root"]["translations"][1] = [0.0, 2.0, 0.0]
    metrics = humanoid_root_motion(animation)
    assert metrics["displacement"] == 0.0
    assert metrics["maxMagnitude"] == 2.0
    assert metrics["worstFrame"] == 1
    assert metrics["isInPlace"] is False
    assert parse_samples("0,2", 3) == [0, 2]
    with pytest.raises(ValueError, match="outside"):
        parse_samples("3", 3)


def test_mapping_profiles_contain_no_animation_authority():
    root = Path(__file__).parents[3]
    for name in ("mixamo_humanoid_v1.json", "derived_humanoid_v1.json"):
        data = json.loads((root / "profiles" / "humanoid_motion" / name).read_text())
        assert set(data) == {"schema", "version", "id", "canonicalSkeleton", "joints"}


def test_release_fixture_manifest_is_immutable_and_records_independent_targets():
    root = Path(__file__).parents[3]
    manifest = json.loads((root / "tests" / "motion" / "humanoid_motion" / "fixtures" / "release_assets.json").read_text())
    assert manifest["releaseTag"] == "e2e_gh_action_asset"
    assert set(manifest["assets"]) == {"character-a", "maria", "warrok", "idle", "run", "run-inplace"}
    for asset in manifest["assets"].values():
        assert f"/releases/download/{manifest['releaseTag']}/" in asset["url"]
        assert "/latest/" not in asset["url"]
        assert re.fullmatch(r"[0-9a-f]{64}", asset["sha256"])
        assert asset["size"] > 0
        assert asset["assetId"].startswith("RA_")
    assert manifest["assets"]["maria"] | {"filename": "Maria.WProp.J.J.Ong.fbx", "sha256": "98794a114b5b252affa1daf600c000e1051e3ede1a477954cdc464eb12c081b9", "size": 15616896} == manifest["assets"]["maria"]
    assert manifest["assets"]["warrok"] | {"filename": "Warrok.W.Kurniawan.fbx", "sha256": "b919cfbca59847285cb95f89f827a682d6f98c7a720047f69d58527c27ae897f", "size": 12072960} == manifest["assets"]["warrok"]


def _source_animation(rig):
    identity = {
        bone["name"]: {"translation": [0.0, 0.0, 0.0], "rotationQuaternion": [1.0, 0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0]}
        for bone in rig["bones"]
    }
    frames = []
    for index, (travel, bounce) in enumerate(((0.0, 0.0), (2.0, 0.2), (4.0, 0.0)), start=1):
        bones = copy.deepcopy(identity)
        bones["bone_Hips"]["translation"] = [0.0, travel, bounce]
        frames.append({"frame": index, "bones": bones})
    return {"id": "source-run", "durationSeconds": 2.0 / 30.0, "fps": 30.0, "frameCount": 3, "frames": frames}


def test_independent_fidelity_oracle_catches_corruption_and_preserves_bounce():
    rig, mapping = _rig_and_mapping()
    source = _source_animation(rig)
    animation = _animation(3)
    animation["hips"]["translations"] = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.1], [0.0, 0.0, 0.0]]
    report = compare_source_to_humanoid_motion(rig, source, mapping, animation)
    assert report["pass"] is True
    assert report["timing"]["durationErrorSeconds"] == 0.0
    assert report["timing"]["durationExactCopy"] is True
    assert report["timing"]["durationWithinTolerance"] is True
    assert report["locomotionStripping"]["sourcePlanarDisplacement"] == pytest.approx(2.0)
    assert report["locomotionStripping"]["actualHipsVerticalRange"] == pytest.approx(0.1)

    corrupted_joint = copy.deepcopy(animation)
    corrupted_joint["joints"]["LeftUpperArm"]["rotations"][1] = [2 ** -0.5, 0.0, 0.0, 2 ** -0.5]
    assert compare_source_to_humanoid_motion(rig, source, mapping, corrupted_joint)["pass"] is False

    lost_bounce = copy.deepcopy(animation)
    lost_bounce["hips"]["translations"][1] = [0.0, 0.0, 0.0]
    failed = compare_source_to_humanoid_motion(rig, source, mapping, lost_bounce)
    assert failed["pass"] is False
    assert failed["maxErrors"]["hipsTranslationMeanLegLength"] > 0.09

    wrong_fps = copy.deepcopy(animation)
    wrong_fps["fps"] = 24.0
    failed = compare_source_to_humanoid_motion(rig, source, mapping, wrong_fps)
    assert failed["pass"] is False
    assert failed["schemaValidation"]["pass"] is False

    wrong_frame_count = _animation(2)
    wrong_frame_count["hips"]["translations"] = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.1]]
    failed = compare_source_to_humanoid_motion(rig, source, mapping, wrong_frame_count)
    assert failed["pass"] is False
    assert failed["timing"]["pass"] is False

    moving_root = copy.deepcopy(animation)
    moving_root["root"]["translations"][1] = [0.01, 0.0, 0.0]
    failed = compare_source_to_humanoid_motion(rig, source, mapping, moving_root)
    assert failed["pass"] is False
    assert failed["schemaValidation"]["pass"] is False

    invalid_quaternion = copy.deepcopy(animation)
    invalid_quaternion["joints"]["Head"]["rotations"][1] = [2.0, 0.0, 0.0, 0.0]
    failed = compare_source_to_humanoid_motion(rig, source, mapping, invalid_quaternion)
    assert failed["pass"] is False
    assert failed["schemaValidation"]["pass"] is False

    changed_source_duration = copy.deepcopy(source)
    changed_source_duration["durationSeconds"] -= 5e-7
    failed = compare_source_to_humanoid_motion(rig, changed_source_duration, mapping, animation)
    assert failed["pass"] is False
    assert failed["timing"]["durationErrorSeconds"] == pytest.approx(5e-7)
    assert failed["timing"]["durationExactCopy"] is False
    assert failed["timing"]["durationWithinTolerance"] is True

    missing_source_duration = copy.deepcopy(source)
    del missing_source_duration["durationSeconds"]
    failed = compare_source_to_humanoid_motion(rig, missing_source_duration, mapping, animation)
    assert failed["pass"] is False
    assert failed["timing"]["durationErrorSeconds"] is None
    assert failed["timing"]["durationExactCopy"] is False
    assert failed["timing"]["durationWithinTolerance"] is False


def test_fidelity_oracle_is_architecturally_independent_from_export_and_playback():
    source = inspect.getsource(__import__("motion2sheet.motion.humanoid_motion.fidelity", fromlist=["*"]))
    for forbidden in ("blender_export", "blender_render", "blender_math", "build_json_scene"):
        assert forbidden not in source
