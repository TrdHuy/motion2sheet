from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from motion2sheet.motion.cli import parser
from motion2sheet.motion.contract_c.mapping import mapping_diagnostics, validate_character_mapping
from motion2sheet.motion.contract_c.root_motion import contract_root_motion
from motion2sheet.motion.contract_c.runner import parse_samples
from motion2sheet.motion.contract_c.schema import (
    ANIMATION_SCHEMA,
    CANONICAL_SKELETON,
    EXPECTED_COORDINATE_SYSTEM,
    EXPECTED_QUATERNION_CONVENTION,
    MAPPED_JOINTS,
    ROTATION_JOINTS,
    validate_animation,
)


def _animation(frame_count=2):
    identity = [1.0, 0.0, 0.0, 0.0]
    return {
        "schema": ANIMATION_SCHEMA,
        "version": 1,
        "id": "run",
        "canonicalSkeleton": "humanoid_v1",
        "fps": 30.0,
        "frameCount": frame_count,
        "loop": True,
        "coordinateSystem": copy.deepcopy(EXPECTED_COORDINATE_SYSTEM),
        "quaternionConvention": copy.deepcopy(EXPECTED_QUATERNION_CONVENTION),
        "root": {
            "translations": [[0.0, float(index), 0.0] for index in range(frame_count)],
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
        head = [0.0, 0.0, 0.0] if parent_name is None else [heads[parent_name][0], heads[parent_name][1] + 1.0, 0.0]
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
        "id": "contract-c-fixture-rig",
        "source": {"format": "BVH", "filename": "fixture.bvh", "sha256": "0" * 64, "importer": "blender-bvh"},
        "coordinateSystem": {"space": "Blender scene after source import", "handedness": "right-handed", "rightAxis": "+X", "forwardAxis": "-Y", "upAxis": "+Z"},
        "units": {"system": "NONE", "metersPerBlenderUnit": 1.0},
        "restAuthority": "editGeometry",
        "editGeometrySpace": "armature-local",
        "armatureObject": {"name": "Armature", "dataName": "Armature", "transform": {"translation": [0.0, 0.0, 0.0], "rotationQuaternion": [1.0, 0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0]}},
        "bones": bones,
    }
    mapping = {"schema": "motion2sheet.contract-c.character-map", "version": 1, "id": "fixture", "canonicalSkeleton": "humanoid_v1", "joints": joints}
    return rig, mapping


def test_public_cli_exposes_contract_c_commands():
    root = parser()
    export = root.parse_args(["export-contract-c-animation", "--source-rig", "rig.json", "--source-animation", "animation.json", "--mapping", "map.json", "--id", "run", "--output", "out"])
    assert export.command == "export-contract-c-animation"
    render = root.parse_args(["render-contract-c-animation", "--model", "model.glb", "--character-rig", "rig.json", "--skin", "skin.json", "--character-mapping", "map.json", "--animation", "animation.json", "--camera-profile", "camera.json5", "--output", "out"])
    assert render.command == "render-contract-c-animation"


def test_contract_c_schema_is_strict_and_complete():
    assert validate_animation(_animation())["frameCount"] == 2
    missing = _animation()
    del missing["joints"]["LeftUpperArm"]
    with pytest.raises(ValueError, match="joint set mismatch"):
        validate_animation(missing)
    world_positions = _animation()
    world_positions["joints"]["Head"]["worldPositions"] = [[0, 0, 0], [0, 0, 0]]
    with pytest.raises(ValueError, match="unknown fields"):
        validate_animation(world_positions)


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


def test_root_motion_and_sample_selection_are_data_driven():
    animation = _animation(3)
    metrics = contract_root_motion(animation)
    assert metrics["displacement"] == 2.0
    assert metrics["direction"] == [0.0, 1.0, 0.0]
    assert metrics["isInPlace"] is False
    assert parse_samples("0,2", 3) == [0, 2]
    with pytest.raises(ValueError, match="outside"):
        parse_samples("3", 3)


def test_mapping_profiles_contain_no_animation_authority():
    root = Path(__file__).parents[3]
    for name in ("mixamo_humanoid_v1.json", "derived_humanoid_v1.json"):
        data = json.loads((root / "profiles" / "contract_c" / name).read_text())
        assert set(data) == {"schema", "version", "id", "canonicalSkeleton", "joints"}
