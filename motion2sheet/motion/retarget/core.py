from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Mapping, Sequence

Vec3 = tuple[float, float, float]
Raw3DFrame = Mapping[str, Sequence[float]]

REQUIRED_SEGMENTS: tuple[str, ...] = (
    "pelvis_neck",
    "neck_head",
    "shoulder_offset",
    "upper_arm",
    "lower_arm",
    "hip_offset",
    "upper_leg",
    "lower_leg",
)


def load_profile(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read proportion profile {path}: {exc}") from exc
    return validate_profile(data)


def validate_profile(profile: dict) -> dict:
    if not isinstance(profile, dict):
        raise ValueError("Proportion profile must be a JSON object")
    name = profile.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Proportion profile name must be a non-empty string")
    segments = profile.get("segments")
    if not isinstance(segments, dict):
        raise ValueError("Proportion profile segments must be a JSON object")

    missing = [key for key in REQUIRED_SEGMENTS if key not in segments]
    if missing:
        raise ValueError(f"Missing proportion profile segments: {', '.join(missing)}")

    normalized: dict[str, float] = {}
    for key in REQUIRED_SEGMENTS:
        try:
            value = float(segments[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Proportion profile segment {key!r} must be numeric") from exc
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"Proportion profile segment {key!r} must be positive and finite")
        normalized[key] = value

    return {
        "name": name.strip(),
        "description": str(profile.get("description", "")),
        "segments": normalized,
    }


def _vec(point: Sequence[float]) -> Vec3:
    if len(point) != 3:
        raise ValueError(f"Expected 3D joint coordinate, got {point!r}")
    return float(point[0]), float(point[1]), float(point[2])


def _add(a: Vec3, b: Vec3) -> Vec3:
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _mul(vector: Vec3, scalar: float) -> Vec3:
    return vector[0] * scalar, vector[1] * scalar, vector[2] * scalar


def _length(vector: Vec3) -> float:
    return math.sqrt(sum(value * value for value in vector))


def _unit(vector: Vec3, label: str) -> Vec3:
    length = _length(vector)
    if not math.isfinite(length) or length < 1e-9:
        raise ValueError(f"Cannot retarget zero-length direction: {label}")
    return _mul(vector, 1.0 / length)


def _direction(frame: Mapping[str, Vec3], parent: str, child: str) -> Vec3:
    return _unit(_sub(frame[child], frame[parent]), f"{parent}->{child}")


def _distance(frame: Raw3DFrame, first: str, second: str) -> float:
    return _length(_sub(_vec(frame[second]), _vec(frame[first])))


def source_stature(frame: Raw3DFrame) -> float:
    left_leg = _distance(frame, "left_hip", "left_knee") + _distance(frame, "left_knee", "left_ankle")
    right_leg = _distance(frame, "right_hip", "right_knee") + _distance(frame, "right_knee", "right_ankle")
    stature = (
        _distance(frame, "pelvis", "neck")
        + _distance(frame, "neck", "head")
        + 0.5 * (left_leg + right_leg)
    )
    if not math.isfinite(stature) or stature <= 1e-9:
        raise ValueError("Source skeleton stature is invalid")
    return stature


def target_stature(profile: dict) -> float:
    segments = profile["segments"]
    return (
        segments["pelvis_neck"]
        + segments["neck_head"]
        + segments["upper_leg"]
        + segments["lower_leg"]
    )


def retarget_frame(frame: Raw3DFrame, profile: dict, *, root_motion_scale: float) -> dict[str, list[float]]:
    segments = profile["segments"]
    source = {name: _vec(point) for name, point in frame.items()}

    required_joints = (
        "pelvis", "neck", "head",
        "left_shoulder", "left_elbow", "left_wrist",
        "right_shoulder", "right_elbow", "right_wrist",
        "left_hip", "left_knee", "left_ankle",
        "right_hip", "right_knee", "right_ankle",
    )
    missing = [joint for joint in required_joints if joint not in source]
    if missing:
        raise ValueError(f"Missing joints for proportion retargeting: {', '.join(missing)}")

    right_axis = _unit(_sub(source["right_hip"], source["left_hip"]), "left_hip->right_hip")
    result: dict[str, Vec3] = {}

    pelvis = _mul(source["pelvis"], root_motion_scale)
    result["pelvis"] = pelvis

    neck = _add(pelvis, _mul(_direction(source, "pelvis", "neck"), segments["pelvis_neck"]))
    result["neck"] = neck
    result["head"] = _add(neck, _mul(_direction(source, "neck", "head"), segments["neck_head"]))

    result["left_shoulder"] = _add(neck, _mul(right_axis, -segments["shoulder_offset"]))
    result["right_shoulder"] = _add(neck, _mul(right_axis, segments["shoulder_offset"]))

    result["left_elbow"] = _add(
        result["left_shoulder"],
        _mul(_direction(source, "left_shoulder", "left_elbow"), segments["upper_arm"]),
    )
    result["left_wrist"] = _add(
        result["left_elbow"],
        _mul(_direction(source, "left_elbow", "left_wrist"), segments["lower_arm"]),
    )
    result["right_elbow"] = _add(
        result["right_shoulder"],
        _mul(_direction(source, "right_shoulder", "right_elbow"), segments["upper_arm"]),
    )
    result["right_wrist"] = _add(
        result["right_elbow"],
        _mul(_direction(source, "right_elbow", "right_wrist"), segments["lower_arm"]),
    )

    result["left_hip"] = _add(pelvis, _mul(right_axis, -segments["hip_offset"]))
    result["right_hip"] = _add(pelvis, _mul(right_axis, segments["hip_offset"]))

    result["left_knee"] = _add(
        result["left_hip"],
        _mul(_direction(source, "left_hip", "left_knee"), segments["upper_leg"]),
    )
    result["left_ankle"] = _add(
        result["left_knee"],
        _mul(_direction(source, "left_knee", "left_ankle"), segments["lower_leg"]),
    )
    result["right_knee"] = _add(
        result["right_hip"],
        _mul(_direction(source, "right_hip", "right_knee"), segments["upper_leg"]),
    )
    result["right_ankle"] = _add(
        result["right_knee"],
        _mul(_direction(source, "right_knee", "right_ankle"), segments["lower_leg"]),
    )

    return {joint: [float(value) for value in point] for joint, point in result.items()}


def retarget_frames(frames: Sequence[Raw3DFrame], profile: dict) -> tuple[list[dict[str, list[float]]], dict]:
    if not frames:
        raise ValueError("Cannot retarget an empty pose sequence")
    normalized_profile = validate_profile(profile)
    source_size = source_stature(frames[0])
    target_size = target_stature(normalized_profile)
    root_motion_scale = target_size / source_size

    result = [
        retarget_frame(frame, normalized_profile, root_motion_scale=root_motion_scale)
        for frame in frames
    ]
    metadata = {
        "profile": normalized_profile["name"],
        "sourceStature": source_size,
        "targetStature": target_size,
        "rootMotionScale": root_motion_scale,
    }
    return result, metadata
