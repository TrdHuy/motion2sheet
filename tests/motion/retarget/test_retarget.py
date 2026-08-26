from __future__ import annotations

import math

import pytest

from motion2sheet.motion.retarget import retarget_frames, validate_profile


PROFILE = {
    "name": "test_chibi",
    "segments": {
        "pelvis_neck": 0.27,
        "neck_head": 0.11,
        "shoulder_offset": 0.16,
        "upper_arm": 0.15,
        "lower_arm": 0.14,
        "hip_offset": 0.09,
        "upper_leg": 0.17,
        "lower_leg": 0.16,
    },
}


def source_frame(phase: float = 0.0, pelvis_z: float = 0.0):
    swing = 0.16 * math.sin(phase)
    return {
        "pelvis": [0.0, 0.0, pelvis_z],
        "neck": [0.0, 0.0, 0.55 + pelvis_z],
        "head": [0.0, 0.0, 0.72 + pelvis_z],
        "left_shoulder": [-0.20, 0.0, 0.56 + pelvis_z],
        "left_elbow": [-0.48, swing, 0.43 + pelvis_z],
        "left_wrist": [-0.68, swing, 0.22 + pelvis_z],
        "right_shoulder": [0.20, 0.0, 0.56 + pelvis_z],
        "right_elbow": [0.48, -swing, 0.43 + pelvis_z],
        "right_wrist": [0.68, -swing, 0.22 + pelvis_z],
        "left_hip": [-0.12, 0.0, pelvis_z],
        "left_knee": [-0.12, swing, -0.42 + pelvis_z],
        "left_ankle": [-0.12, 0.0, -0.84 + pelvis_z],
        "right_hip": [0.12, 0.0, pelvis_z],
        "right_knee": [0.12, -swing, -0.42 + pelvis_z],
        "right_ankle": [0.12, 0.0, -0.84 + pelvis_z],
    }


def distance(frame, first, second):
    a, b = frame[first], frame[second]
    return math.dist(a, b)


def test_retarget_enforces_profile_lengths_and_preserves_motion():
    frames, metadata = retarget_frames(
        [source_frame(0.0), source_frame(math.pi / 2.0, pelvis_z=0.04)],
        PROFILE,
    )

    for frame in frames:
        assert distance(frame, "pelvis", "neck") == pytest.approx(0.27)
        assert distance(frame, "neck", "head") == pytest.approx(0.11)
        assert distance(frame, "left_shoulder", "left_elbow") == pytest.approx(0.15)
        assert distance(frame, "left_elbow", "left_wrist") == pytest.approx(0.14)
        assert distance(frame, "left_hip", "left_knee") == pytest.approx(0.17)
        assert distance(frame, "left_knee", "left_ankle") == pytest.approx(0.16)
        assert distance(frame, "right_hip", "right_knee") == pytest.approx(0.17)
        assert distance(frame, "right_knee", "right_ankle") == pytest.approx(0.16)
        assert frame["left_hip"][0] < frame["right_hip"][0]
        assert frame["left_shoulder"][0] < frame["right_shoulder"][0]

    assert frames[0]["left_knee"] != frames[1]["left_knee"]
    assert frames[1]["pelvis"][2] > frames[0]["pelvis"][2]
    assert metadata["profile"] == "test_chibi"
    assert metadata["rootMotionScale"] > 0


def test_profile_validation_rejects_missing_or_invalid_segments():
    invalid = {"name": "bad", "segments": dict(PROFILE["segments"])}
    invalid["segments"].pop("upper_leg")
    with pytest.raises(ValueError, match="Missing proportion profile segments"):
        validate_profile(invalid)

    invalid = {"name": "bad", "segments": dict(PROFILE["segments"])}
    invalid["segments"]["upper_leg"] = 0
    with pytest.raises(ValueError, match="positive and finite"):
        validate_profile(invalid)
