from __future__ import annotations

import copy
import math

import pytest

from motion2sheet.motion.skin import (
    diagnose_level1_rig_compatibility,
    validate_level1_rig_compatibility,
)

SOURCE_SHA = "0" * 64


def _transform(translation=(0.0, 0.0, 0.0)):
    return {
        "translation": list(translation),
        "rotationQuaternion": [1.0, 0.0, 0.0, 0.0],
        "scale": [1.0, 1.0, 1.0],
    }


def _properties(*, connected=False):
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


def _rig():
    return {
        "schema": "motion2sheet.source-rig",
        "version": 1,
        "id": "diagnostic-rig-v1",
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
            "transform": _transform(),
        },
        "bones": [
            {
                "name": "Root",
                "parent": None,
                "rest": _transform(),
                "length": 1.0,
                "editGeometry": {
                    "head": [0.0, 0.0, 0.0],
                    "tail": [0.0, 1.0, 0.0],
                    "roll": 0.0,
                },
                "properties": _properties(),
            },
            {
                "name": "Child",
                "parent": "Root",
                "rest": _transform((0.0, 1.0, 0.0)),
                "length": 0.5,
                "editGeometry": {
                    "head": [0.0, 1.0, 0.0],
                    "tail": [0.0, 1.5, 0.0],
                    "roll": 0.0,
                },
                "properties": _properties(connected=True),
            },
        ],
    }


def test_level1_diagnostic_pass_report_is_complete_and_non_mutating():
    source = _rig()
    target = copy.deepcopy(source)
    report = diagnose_level1_rig_compatibility(source, target)

    assert report["pass"] is True
    assert report["level"] == 1
    assert report["boneCount"] == 2
    assert report["exactBoneNames"] is True
    assert report["exactHierarchy"] is True
    assert report["coordinateConventionMatch"] is True
    assert report["missingBones"] == []
    assert report["extraBones"] == []
    assert report["parentMismatches"] == []
    assert report["coordinateMismatches"] == []
    assert report["restBasisMismatchCount"] == 0
    assert report["restBasisMismatches"] == []
    assert report["restBasisToleranceDegrees"] == 0.001
    assert report["retargeting"] is False
    assert report["fuzzyMapping"] is False
    assert source == _rig()


def test_level1_diagnostic_collects_all_rest_basis_mismatches():
    source = _rig()
    target = copy.deepcopy(source)
    target["bones"][0]["editGeometry"]["roll"] = math.radians(2.0)
    target["bones"][1]["editGeometry"]["roll"] = math.radians(5.0)

    report = diagnose_level1_rig_compatibility(source, target)

    assert report["pass"] is False
    assert report["restBasisMismatchCount"] == 2
    assert [item["bone"] for item in report["restBasisMismatches"]] == ["Child", "Root"]
    errors = {item["bone"]: item["errorDegrees"] for item in report["restBasisMismatches"]}
    assert errors["Root"] == pytest.approx(2.0, abs=1e-7)
    assert errors["Child"] == pytest.approx(3.0, abs=1e-7)
    assert report["maxRestBasisErrorDegrees"] == pytest.approx(3.0, abs=1e-7)
    assert report["worstRestBasisBone"] == "Child"

    # Strict API keeps historical fail-closed ordering: first mismatching bone by name.
    with pytest.raises(ValueError, match=r"rest-basis mismatch for Child"):
        validate_level1_rig_compatibility(source, target)


def test_level1_diagnostic_collects_structural_and_coordinate_mismatches():
    source = _rig()
    target = copy.deepcopy(source)
    target["bones"][1]["parent"] = None
    target["bones"][1]["properties"]["useConnect"] = False
    target["coordinateSystem"]["upAxis"] = "+Y"

    report = diagnose_level1_rig_compatibility(source, target)

    assert report["pass"] is False
    assert report["exactBoneNames"] is True
    assert report["exactHierarchy"] is False
    assert report["coordinateConventionMatch"] is False
    assert report["parentMismatches"] == [
        {"bone": "Child", "animationParent": "Root", "characterParent": None}
    ]
    assert report["coordinateMismatches"] == [
        {"field": "upAxis", "animation": "+Z", "character": "+Y"}
    ]
    assert report["maxRestBasisErrorDegrees"] is None
    assert report["restBasisMismatches"] == []

    # Validator preserves parent-before-coordinate failure priority.
    with pytest.raises(ValueError, match=r"parent mismatch for Child"):
        validate_level1_rig_compatibility(source, target)
