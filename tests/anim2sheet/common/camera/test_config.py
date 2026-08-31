from __future__ import annotations

import pytest

from motion2sheet.anim2sheet.common.camera.config import (
    final_camera_name,
    resolve_camera_names,
    validate_camera_profile,
)


def profile():
    return {
        "version": 1,
        "defaultReviewCameras": ["front_final", "side_diag"],
        "cameras": {
            "front_final": {
                "role": "final",
                "projection": "orthographic",
                "position": [0, -8, 1.2],
                "rotationDeg": [90, 0, 0],
                "orthoScale": 3.6,
            },
            "side_diag": {
                "role": "diagnostic",
                "projection": "perspective",
                "position": [8, 0, 1.2],
                "rotationDeg": [90, 0, 90],
                "focalLengthMm": 50,
            },
        },
    }


def test_defaults_and_explicit_selection():
    data = validate_camera_profile(profile())
    assert resolve_camera_names(data) == ["front_final", "side_diag"]
    assert resolve_camera_names(data, "side_diag,front_final") == ["side_diag", "front_final"]
    assert final_camera_name(data, ["front_final", "side_diag"]) == "front_final"


def test_unknown_and_duplicate_requests_fail():
    data = validate_camera_profile(profile())
    with pytest.raises(ValueError, match="unknown cameras"):
        resolve_camera_names(data, "missing")
    with pytest.raises(ValueError, match="duplicate cameras"):
        resolve_camera_names(data, "front_final,front_final")


def test_invalid_projection_and_sizes_fail():
    data = profile()
    data["cameras"]["front_final"]["projection"] = "fisheye"
    with pytest.raises(ValueError, match="projection"):
        validate_camera_profile(data)
    data = profile()
    data["cameras"]["front_final"]["orthoScale"] = 0
    with pytest.raises(ValueError, match="orthoScale"):
        validate_camera_profile(data)
    data = profile()
    data["cameras"]["side_diag"]["focalLengthMm"] = -1
    with pytest.raises(ValueError, match="focalLengthMm"):
        validate_camera_profile(data)


def test_missing_fields_and_duplicate_defaults_fail():
    data = profile()
    del data["cameras"]["front_final"]["position"]
    with pytest.raises(ValueError, match="position"):
        validate_camera_profile(data)
    data = profile()
    data["defaultReviewCameras"] = ["front_final", "front_final"]
    with pytest.raises(ValueError, match="duplicate"):
        validate_camera_profile(data)
