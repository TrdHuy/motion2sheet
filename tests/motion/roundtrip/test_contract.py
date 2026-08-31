from pathlib import Path

import pytest

from motion2sheet.motion.roundtrip.schema import canonical_json_text, validate_animation_document, validate_rig_document


def transform():
    return {"translation": [0.0, 0.0, 0.0], "rotationQuaternion": [1.0, 0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0]}


def rig():
    return {
        "schema": "motion2sheet.source-rig", "version": 1, "id": "fixture-rig-v1",
        "armatureObject": {"transform": transform()},
        "bones": [
            {"name": "Root", "parent": None, "rest": transform(), "length": 1.0, "properties": {}},
            {"name": "Child", "parent": "Root", "rest": transform(), "length": 0.5, "properties": {}},
        ],
    }


def animation():
    frames = []
    for frame in (1, 2):
        frames.append({"frame": frame, "bones": {"Root": transform(), "Child": transform()}})
    return {
        "schema": "motion2sheet.source-animation", "version": 1, "id": "fixture-animation-v1",
        "rig": {"id": "fixture-rig-v1"}, "fps": 30.0, "frameRange": [1, 2], "frameCount": 2,
        "frames": frames,
    }


def test_contract_is_deterministic_and_human_readable():
    first = canonical_json_text({"z": 1.0, "a": {"value": 2.0}})
    second = canonical_json_text({"a": {"value": 2.0}, "z": 1.0})
    assert first == second
    assert first.startswith('{\n  "a"')


def test_rig_and_animation_validate():
    validated_rig = validate_rig_document(rig())
    validate_animation_document(animation(), validated_rig)


def test_animation_frames_must_be_contiguous():
    validated_rig = validate_rig_document(rig())
    data = animation()
    data["frames"][1]["frame"] = 3
    with pytest.raises(ValueError, match="ordered and contiguous"):
        validate_animation_document(data, validated_rig)


def test_animation_must_contain_every_rig_bone():
    validated_rig = validate_rig_document(rig())
    data = animation()
    del data["frames"][0]["bones"]["Child"]
    with pytest.raises(ValueError, match="bone set mismatch"):
        validate_animation_document(data, validated_rig)


def test_quaternion_must_be_normalized():
    data = rig()
    data["bones"][0]["rest"]["rotationQuaternion"] = [2.0, 0.0, 0.0, 0.0]
    with pytest.raises(ValueError, match="normalized"):
        validate_rig_document(data)
