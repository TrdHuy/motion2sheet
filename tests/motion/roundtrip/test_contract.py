import pytest

from motion2sheet.motion.roundtrip.schema import canonical_json_text, validate_animation_document, validate_rig_document


def transform():
    return {"translation": [0.0, 0.0, 0.0], "rotationQuaternion": [1.0, 0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0]}


def geometry(head, tail, roll=0.0):
    return {"head": list(head), "tail": list(tail), "roll": roll}


def rig():
    return {
        "schema": "motion2sheet.source-rig", "version": 1, "id": "fixture-rig-v1",
        "editGeometrySpace": "armature-local",
        "armatureObject": {"transform": transform()},
        "bones": [
            {
                "name": "Root", "parent": None, "rest": transform(), "length": 1.0,
                "editGeometry": geometry((0.0, 0.0, 0.0), (0.0, 1.0, 0.0)), "properties": {},
            },
            {
                "name": "Child", "parent": "Root", "rest": transform(), "length": 0.5,
                "editGeometry": geometry((0.0, 1.0, 0.0), (0.0, 1.5, 0.0), 0.125), "properties": {},
            },
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


def fbx_animation_metadata():
    return {
        "stack": "Take 001",
        "layer": "BaseLayer",
        "stackTiming": {
            "LocalStart": 0,
            "LocalStop": 1,
            "ReferenceStart": 0,
            "ReferenceStop": 1,
        },
        "sampling": "all-integer-source-frames",
        "sampleKeyTimes": [0, 1],
    }


def test_contract_is_deterministic_and_human_readable():
    first = canonical_json_text({"z": 1.0, "a": {"value": 2.0}})
    second = canonical_json_text({"a": {"value": 2.0}, "z": 1.0})
    assert first == second
    assert first.startswith('{\n  "a"')


def test_rig_and_animation_validate():
    validated_rig = validate_rig_document(rig())
    validate_animation_document(animation(), validated_rig)


def test_rig_requires_explicit_edit_geometry():
    data = rig()
    del data["bones"][0]["editGeometry"]
    with pytest.raises(ValueError, match="editGeometry"):
        validate_rig_document(data)


def test_edit_geometry_must_define_nonzero_bone():
    data = rig()
    data["bones"][0]["editGeometry"]["tail"] = [0.0, 0.0, 0.0]
    with pytest.raises(ValueError, match="non-zero"):
        validate_rig_document(data)


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


def test_fbx_static_encoding_metadata_is_allowed_without_motion_curves():
    validated_rig = validate_rig_document(rig())
    data = animation()
    data["source"] = {"format": "FBX"}
    data["sourceFormat"] = {"fbx": fbx_animation_metadata()}
    validate_animation_document(data, validated_rig)


def test_fbx_native_curve_values_are_forbidden_in_canonical_animation():
    validated_rig = validate_rig_document(rig())
    data = animation()
    data["source"] = {"format": "FBX"}
    metadata = fbx_animation_metadata()
    metadata["curves"] = [
        {
            "bone": "Root",
            "property": "rotation",
            "axis": "x",
            "keyTimes": [0, 1],
            "keyValues": [10.0, 20.0],
        }
    ]
    data["sourceFormat"] = {"fbx": metadata}
    with pytest.raises(ValueError, match="sole motion authority"):
        validate_animation_document(data, validated_rig)
