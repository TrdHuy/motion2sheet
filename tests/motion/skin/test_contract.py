from __future__ import annotations

import copy
import hashlib
import math

import pytest

from motion2sheet.motion.skin import (
    build_skin_document,
    canonical_json_bytes,
    compare_skin_bindings,
    normalize_influences,
    skin_statistics,
    validate_level1_rig_compatibility,
    validate_skin_document,
    verify_model_identity,
    vertex_order_hash,
)

SOURCE_SHA = "0" * 64
IDENTITY16 = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]


def transform(translation=(0.0, 0.0, 0.0), quaternion=(1.0, 0.0, 0.0, 0.0)):
    return {
        "translation": list(translation),
        "rotationQuaternion": list(quaternion),
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


def rig(*, scale=1.0):
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
        "armatureObject": {"name": "Armature", "dataName": "Armature", "transform": transform()},
        "bones": [
            {
                "name": "Root",
                "parent": None,
                "rest": transform(),
                "length": 1.0 * scale,
                "editGeometry": geometry((0.0, 0.0, 0.0), (0.0, 1.0 * scale, 0.0)),
                "properties": bone_properties(),
            },
            {
                "name": "Child",
                "parent": "Root",
                "rest": transform((0.0, 1.0 * scale, 0.0)),
                "length": 0.5 * scale,
                "editGeometry": geometry((0.0, 1.0 * scale, 0.0), (0.0, 1.5 * scale, 0.0)),
                "properties": bone_properties(connected=True),
            },
        ],
    }


def raw_mesh(*, reverse_weights=False):
    weights = [
        {"vertex": 0, "influences": [["Root", 2.0], ["Child", 1.0]]},
        {"vertex": 1, "influences": [["Child", 7.0]]},
    ]
    if reverse_weights:
        weights.reverse()
        weights[1]["influences"].reverse()
    return {
        "object": "Character",
        "vertexCount": 3,
        "vertexOrderHash": vertex_order_hash([(0, 0, 0), (1, 0, 0), (0, 1, 0)]),
        "objectTransform": IDENTITY16,
        "armatureModifier": {"name": "Armature", "object": "Armature"},
        "weights": weights,
    }


def build_skin(character_rig=None, *, reverse_weights=False, model_sha="1" * 64):
    character_rig = character_rig or rig()
    return build_skin_document(
        skin_id="fixture-skin-v1",
        canonical_rig="mixamo-compatible-v1",
        character_rig=character_rig,
        model={
            "filename": "model.glb",
            "format": "GLB",
            "sha256": model_sha,
            "coordinateSystem": copy.deepcopy(character_rig["coordinateSystem"]),
        },
        bind={
            "mode": "blender-armature-modifier-v1",
            "restConvention": "blender-edit-bone-y-axis-roll-v1",
            "armatureObject": "Armature",
            "armatureObjectTransform": IDENTITY16,
        },
        meshes=[raw_mesh(reverse_weights=reverse_weights)],
    )


def test_skin_schema_and_statistics():
    character_rig = rig()
    skin = build_skin(character_rig)
    assert validate_skin_document(skin, character_rig) is skin
    assert skin_statistics(skin, character_rig) == {
        "meshCount": 1,
        "vertexCount": 3,
        "weightedVertexCount": 2,
        "influenceCount": 3,
        "boneCount": 2,
        "unknownBoneReferences": 0,
    }


def test_skin_build_is_deterministic_across_input_order():
    first = build_skin(reverse_weights=False)
    second = build_skin(reverse_weights=True)
    assert canonical_json_bytes(first) == canonical_json_bytes(second)


def test_weights_are_normalized_and_influences_sorted():
    normalized = normalize_influences([["Root", 2.0], ["Child", 1.0]])
    assert [item[0] for item in normalized] == ["Child", "Root"]
    assert normalized[0][1] == pytest.approx(1.0 / 3.0)
    assert normalized[1][1] == pytest.approx(2.0 / 3.0)
    assert sum(item[1] for item in normalized) == pytest.approx(1.0)


def test_unknown_skin_bone_fails_closed():
    character_rig = rig()
    skin = build_skin(character_rig)
    skin["boneTable"].append("Unknown")
    skin["boneTable"].sort()
    skin["meshes"][0]["weights"][0]["influences"] = [["Child", 0.5], ["Unknown", 0.5]]
    with pytest.raises(ValueError, match="unknown character-rig bones"):
        validate_skin_document(skin, character_rig)


def test_model_vertex_hash_mismatch_fails_closed(tmp_path):
    model = tmp_path / "model.glb"
    model.write_bytes(b"fixture-glb")
    skin = build_skin(model_sha=hashlib.sha256(model.read_bytes()).hexdigest())
    with pytest.raises(ValueError, match="vertex-order hash mismatch"):
        verify_model_identity(
            skin,
            model,
            [{"object": "Character", "vertexCount": 3, "vertexOrderHash": "f" * 64}],
        )


def test_missing_model_mesh_fails_closed(tmp_path):
    model = tmp_path / "model.glb"
    model.write_bytes(b"fixture-glb")
    skin = build_skin(model_sha=hashlib.sha256(model.read_bytes()).hexdigest())
    with pytest.raises(ValueError, match="model mesh set mismatch"):
        verify_model_identity(skin, model, [])


def test_skin_reconstruction_exact_binding_passes():
    reference = build_skin()
    report = compare_skin_bindings(reference, copy.deepcopy(reference))
    assert report["pass"] is True
    assert report["sameMeshObjects"] is True
    assert report["sameVertexCounts"] is True
    assert report["sameVertexOrder"] is True
    assert report["sameInfluencedBones"] is True
    assert report["weightedVertexCount"] == 2
    assert report["influenceCount"] == 3
    assert report["maxWeightDelta"] == 0.0
    assert report["worst"] is None


def test_skin_reconstruction_weight_drift_reports_strict_failure():
    reference = build_skin()
    reconstructed = copy.deepcopy(reference)
    influences = reconstructed["meshes"][0]["weights"][0]["influences"]
    influences[0][1] += 1e-5
    influences[1][1] -= 1e-5
    report = compare_skin_bindings(reference, reconstructed, tolerance=1e-8)
    assert report["pass"] is False
    assert report["maxWeightDelta"] == pytest.approx(1e-5)
    assert report["worst"]["mesh"] == "Character"
    assert report["worst"]["vertex"] == 0


def test_skin_reconstruction_influenced_bone_mismatch_fails_closed():
    reference = build_skin()
    reconstructed = copy.deepcopy(reference)
    reconstructed["boneTable"].append("Other")
    reconstructed["boneTable"].sort()
    reconstructed["meshes"][0]["weights"][0]["influences"] = [["Other", 1.0 / 3.0], ["Root", 2.0 / 3.0]]
    with pytest.raises(ValueError, match="influenced-bone set mismatch"):
        compare_skin_bindings(reference, reconstructed)


def test_level1_allows_different_lengths_with_same_rest_basis():
    report = validate_level1_rig_compatibility(rig(scale=1.0), rig(scale=1.7))
    assert report["pass"] is True
    assert report["boneCount"] == 2
    assert report["maxRestBasisErrorDegrees"] <= 1e-8
    assert report["retargeting"] is False
    assert report["fuzzyMapping"] is False


def test_level1_rest_basis_mismatch_fails_closed():
    target = rig()
    angle = math.radians(2.0)
    target["bones"][1]["editGeometry"]["roll"] = angle
    target["bones"][1]["rest"]["rotationQuaternion"] = [math.cos(angle / 2.0), 0.0, math.sin(angle / 2.0), 0.0]
    with pytest.raises(ValueError, match="rest-basis mismatch"):
        validate_level1_rig_compatibility(rig(), target)


def test_level1_missing_bone_fails_closed():
    target = rig()
    target["bones"] = target["bones"][:1]
    with pytest.raises(ValueError, match="bone set mismatch"):
        validate_level1_rig_compatibility(rig(), target)


def test_level1_extra_bone_fails_closed():
    target = rig()
    extra = copy.deepcopy(target["bones"][1])
    extra["name"] = "Extra"
    extra["parent"] = None
    extra["properties"]["useConnect"] = False
    extra["editGeometry"] = geometry((1.0, 0.0, 0.0), (1.0, 0.5, 0.0))
    extra["rest"] = transform((1.0, 0.0, 0.0))
    target["bones"].append(extra)
    with pytest.raises(ValueError, match="bone set mismatch"):
        validate_level1_rig_compatibility(rig(), target)


def test_level1_parent_mismatch_fails_closed():
    target = rig()
    target["bones"][1]["parent"] = None
    target["bones"][1]["properties"]["useConnect"] = False
    with pytest.raises(ValueError, match="parent mismatch"):
        validate_level1_rig_compatibility(rig(), target)
