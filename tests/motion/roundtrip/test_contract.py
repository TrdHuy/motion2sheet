import pytest

from motion2sheet.motion.roundtrip.schema import canonical_json_text, validate_animation_document, validate_rig_document


SOURCE_SHA = "0" * 64


def transform(translation=(0.0, 0.0, 0.0)):
    return {
        "translation": list(translation),
        "rotationQuaternion": [1.0, 0.0, 0.0, 0.0],
        "scale": [1.0, 1.0, 1.0],
    }


def geometry(head, tail, roll=0.0):
    return {"head": list(head), "tail": list(tail), "roll": roll}


def bone_properties(*, connected=False):
    return {
        "useConnect": connected,
        "useDeform": True,
        "useInheritRotation": True,
        "useLocalLocation": True,
        "inheritScale": "FULL",
        "headRadius": 0.1,
        "tailRadius": 0.1,
        "envelopeDistance": 0.25,
        "envelopeWeight": 1.0,
        "useRelativeParent": False,
    }


def rig():
    return {
        "schema": "motion2sheet.source-rig",
        "version": 1,
        "id": "fixture-rig-v1",
        "source": {
            "format": "BVH",
            "filename": "fixture.bvh",
            "sha256": SOURCE_SHA,
            "importer": "blender-bvh",
        },
        "coordinateSystem": {
            "space": "Blender scene after source import",
            "handedness": "right-handed",
            "rightAxis": "+X",
            "forwardAxis": "-Y",
            "upAxis": "+Z",
        },
        "units": {"system": "NONE", "metersPerBlenderUnit": 1.0},
        "restAuthority": "editGeometry",
        "editGeometrySpace": "armature-local",
        "armatureObject": {
            "name": "Armature",
            "dataName": "Armature",
            "transform": transform(),
        },
        "bones": [
            {
                "name": "Root",
                "parent": None,
                "rest": transform(),
                "length": 1.0,
                "editGeometry": geometry((0.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
                "properties": bone_properties(),
            },
            {
                "name": "Child",
                "parent": "Root",
                "rest": transform((0.0, 1.0, 0.0)),
                "length": 0.5,
                "editGeometry": geometry((0.0, 1.0, 0.0), (0.0, 1.5, 0.0)),
                "properties": bone_properties(connected=True),
            },
        ],
    }


def animation():
    frames = []
    for frame in (1, 2):
        frames.append({"frame": frame, "bones": {"Root": transform(), "Child": transform()}})
    return {
        "schema": "motion2sheet.source-animation",
        "version": 1,
        "id": "fixture-animation-v1",
        "rig": {"id": "fixture-rig-v1"},
        "source": {
            "format": "BVH",
            "filename": "fixture.bvh",
            "sha256": SOURCE_SHA,
            "action": "fixture-action",
        },
        "fps": 30.0,
        "fpsNumerator": 30,
        "fpsBase": 1.0,
        "frameRange": [1, 2],
        "frameCount": 2,
        "sampling": {
            "policy": "all-integer-source-frames-inclusive",
            "step": 1,
            "continuousSubframeBehaviorPreserved": False,
        },
        "transformSpace": {
            "name": "blender-pose-matrix-basis",
            "description": "Per-bone PoseBone.matrix_basis: pose-local delta relative to the bone rest basis, serialized as TRS.",
        },
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


def make_fbx_animation():
    data = animation()
    data["source"]["format"] = "FBX"
    data["source"]["filename"] = "fixture.fbx"
    data["sourceFormat"] = {"fbx": fbx_animation_metadata()}
    return data


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


def test_rest_cache_conflict_with_edit_geometry_is_rejected():
    data = rig()
    data["bones"][1]["rest"]["translation"][0] = 0.1
    with pytest.raises(ValueError, match="conflicts with canonical editGeometry"):
        validate_rig_document(data)


def test_length_cache_conflict_with_edit_geometry_is_rejected():
    data = rig()
    data["bones"][1]["length"] = 0.75
    with pytest.raises(ValueError, match="conflicts with canonical editGeometry"):
        validate_rig_document(data)


def test_edit_geometry_conflict_with_derived_cache_is_rejected():
    data = rig()
    data["bones"][1]["editGeometry"]["tail"][0] = 0.1
    with pytest.raises(ValueError, match="conflicts with canonical editGeometry"):
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


def test_animation_top_level_unknown_field_is_rejected():
    validated_rig = validate_rig_document(rig())
    data = animation()
    data["motionOverride"] = {"Root": "something"}
    with pytest.raises(ValueError, match="unknown fields.*motionOverride"):
        validate_animation_document(data, validated_rig)


def test_rig_top_level_unknown_field_is_rejected():
    data = rig()
    data["restOverride"] = True
    with pytest.raises(ValueError, match="unknown fields.*restOverride"):
        validate_rig_document(data)


def test_bone_unknown_field_is_rejected():
    data = rig()
    data["bones"][0]["extraRest"] = transform()
    with pytest.raises(ValueError, match="unknown fields.*extraRest"):
        validate_rig_document(data)


def test_frame_unknown_field_is_rejected():
    validated_rig = validate_rig_document(rig())
    data = animation()
    data["frames"][0]["override"] = True
    with pytest.raises(ValueError, match="unknown fields.*override"):
        validate_animation_document(data, validated_rig)


def test_nested_unknown_field_is_rejected():
    data = rig()
    data["coordinateSystem"]["extraAxis"] = "+W"
    with pytest.raises(ValueError, match="unknown fields.*extraAxis"):
        validate_rig_document(data)


def test_missing_required_top_level_field_is_rejected():
    data = animation()
    del data["sampling"]
    with pytest.raises(ValueError, match="missing fields.*sampling"):
        validate_animation_document(data, validate_rig_document(rig()))


def test_missing_required_nested_field_is_rejected():
    data = rig()
    del data["armatureObject"]["dataName"]
    with pytest.raises(ValueError, match="missing fields.*dataName"):
        validate_rig_document(data)


def test_fbx_static_encoding_metadata_is_allowed_without_motion_curves():
    validated_rig = validate_rig_document(rig())
    validate_animation_document(make_fbx_animation(), validated_rig)


def test_fbx_native_curve_values_are_forbidden_in_canonical_animation():
    validated_rig = validate_rig_document(rig())
    data = make_fbx_animation()
    data["sourceFormat"]["fbx"]["curves"] = [
        {
            "bone": "Root",
            "property": "rotation",
            "axis": "x",
            "keyTimes": [0, 1],
            "keyValues": [10.0, 20.0],
        }
    ]
    with pytest.raises(ValueError, match="sole motion authority"):
        validate_animation_document(data, validated_rig)
