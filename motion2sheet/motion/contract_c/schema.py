from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

ANIMATION_SCHEMA = "motion2sheet.contract-c.animation"
CANONICAL_SKELETON_ID = "humanoid_v1"
VERSION = 1
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
QUATERNION_NORM_TOLERANCE = 1e-8
QUATERNION_CONTINUITY_TOLERANCE = 1e-12

# Root is a virtual scene-space locomotion parent. Every other semantic is
# explicitly mapped to one target bone.
CANONICAL_SKELETON: dict[str, str | None] = {
    "Root": None,
    "Hips": "Root",
    "Spine": "Hips",
    "Chest": "Spine",
    "Neck": "Chest",
    "Head": "Neck",
    "LeftShoulder": "Chest",
    "LeftUpperArm": "LeftShoulder",
    "LeftLowerArm": "LeftUpperArm",
    "LeftHand": "LeftLowerArm",
    "RightShoulder": "Chest",
    "RightUpperArm": "RightShoulder",
    "RightLowerArm": "RightUpperArm",
    "RightHand": "RightLowerArm",
    "LeftUpperLeg": "Hips",
    "LeftLowerLeg": "LeftUpperLeg",
    "LeftFoot": "LeftLowerLeg",
    "LeftToe": "LeftFoot",
    "RightUpperLeg": "Hips",
    "RightLowerLeg": "RightUpperLeg",
    "RightFoot": "RightLowerLeg",
    "RightToe": "RightFoot",
}
MAPPED_JOINTS = tuple(name for name in CANONICAL_SKELETON if name != "Root")
ROTATION_JOINTS = tuple(name for name in MAPPED_JOINTS if name != "Hips")

EXPECTED_COORDINATE_SYSTEM = {
    "handedness": "right-handed",
    "rightAxis": "+X",
    "forwardAxis": "-Y",
    "upAxis": "+Z",
    "translationUnit": "mean-leg-length",
}
EXPECTED_QUATERNION_CONVENTION = {
    "componentOrder": "wxyz",
    "deltaSpace": "canonical-scene-rest-relative-left-delta",
    "signPolicy": "continuous-nearest-hemisphere",
}


def _object(value: Any, label: str, required: set[str], optional: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    allowed = required | (optional or set())
    missing = required - set(value)
    unknown = set(value) - allowed
    if missing:
        raise ValueError(f"{label} missing fields: {sorted(missing)}")
    if unknown:
        raise ValueError(f"{label} has unknown fields: {sorted(unknown)}")
    return value


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return 0.0 if result == 0.0 else result


def _vector(value: Any, size: int, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != size:
        raise ValueError(f"{label} must contain exactly {size} numbers")
    return [_finite(component, f"{label}[{index}]") for index, component in enumerate(value)]


def _track(value: Any, size: int, frame_count: int, label: str, *, optional: bool = False) -> list[list[float]]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    if optional and not value:
        return []
    if len(value) != frame_count:
        raise ValueError(f"{label} must contain exactly frameCount={frame_count} samples")
    return [_vector(sample, size, f"{label}[{index}]") for index, sample in enumerate(value)]


def _quaternion_track(value: Any, frame_count: int, label: str) -> list[list[float]]:
    track = _track(value, 4, frame_count, label)
    previous: list[float] | None = None
    for index, quaternion in enumerate(track):
        norm = math.sqrt(sum(component * component for component in quaternion))
        if abs(norm - 1.0) > QUATERNION_NORM_TOLERANCE:
            raise ValueError(f"{label}[{index}] must be normalized; norm={norm:.12g}")
        if previous is None:
            first = next((component for component in quaternion if abs(component) > 1e-15), 0.0)
            if first < 0.0:
                raise ValueError(f"{label}[0] must use the lexicographic-positive quaternion sign")
        else:
            dot = sum(a * b for a, b in zip(previous, quaternion))
            if dot < -QUATERNION_CONTINUITY_TOLERANCE:
                raise ValueError(f"{label}[{index}] is not sign-continuous with the previous sample")
            if abs(dot) <= QUATERNION_CONTINUITY_TOLERANCE:
                first = next((component for component in quaternion if abs(component) > 1e-15), 0.0)
                if first < 0.0:
                    raise ValueError(f"{label}[{index}] must use the deterministic tie-break sign")
        previous = quaternion
    return track


def validate_animation(value: Any) -> dict[str, Any]:
    document = _object(
        value,
        "Contract C animation",
        {
            "schema", "version", "id", "canonicalSkeleton", "fps", "frameCount", "loop",
            "coordinateSystem", "quaternionConvention", "root", "hips", "joints",
        },
    )
    if document["schema"] != ANIMATION_SCHEMA or document["version"] != VERSION:
        raise ValueError("unsupported Contract C animation schema/version")
    if not isinstance(document["id"], str) or not ID_RE.fullmatch(document["id"]):
        raise ValueError(f"Contract C animation id must match {ID_RE.pattern}")
    if document["canonicalSkeleton"] != CANONICAL_SKELETON_ID:
        raise ValueError(f"canonicalSkeleton must be {CANONICAL_SKELETON_ID!r}")
    fps = _finite(document["fps"], "fps")
    if fps <= 0.0:
        raise ValueError("fps must be positive")
    if isinstance(document["frameCount"], bool) or not isinstance(document["frameCount"], int) or document["frameCount"] <= 0:
        raise ValueError("frameCount must be a positive integer")
    frame_count = document["frameCount"]
    if not isinstance(document["loop"], bool):
        raise ValueError("loop must be boolean")
    coordinate = _object(document["coordinateSystem"], "coordinateSystem", set(EXPECTED_COORDINATE_SYSTEM))
    if coordinate != EXPECTED_COORDINATE_SYSTEM:
        raise ValueError("coordinateSystem does not match humanoid_v1")
    convention = _object(document["quaternionConvention"], "quaternionConvention", set(EXPECTED_QUATERNION_CONVENTION))
    if convention != EXPECTED_QUATERNION_CONVENTION:
        raise ValueError("quaternionConvention does not match Contract C v1")

    root = _object(document["root"], "root", {"translations", "rotations"})
    root["translations"] = _track(root["translations"], 3, frame_count, "root.translations")
    root["rotations"] = _quaternion_track(root["rotations"], frame_count, "root.rotations")
    hips = _object(document["hips"], "hips", {"translations", "rotations"})
    hips["translations"] = _track(hips["translations"], 3, frame_count, "hips.translations", optional=True)
    hips["rotations"] = _quaternion_track(hips["rotations"], frame_count, "hips.rotations")

    joints = document["joints"]
    if not isinstance(joints, dict) or set(joints) != set(ROTATION_JOINTS):
        missing = set(ROTATION_JOINTS) - set(joints or {})
        extra = set(joints or {}) - set(ROTATION_JOINTS)
        raise ValueError(f"Contract C joint set mismatch; missing={sorted(missing)} extra={sorted(extra)}")
    for semantic in ROTATION_JOINTS:
        row = _object(joints[semantic], f"joints.{semantic}", {"rotations"})
        row["rotations"] = _quaternion_track(row["rotations"], frame_count, f"joints.{semantic}.rotations")
    return document


def canonical_json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False, separators=(",", ": ")) + "\n"


def read_animation(path: Path) -> dict[str, Any]:
    return validate_animation(json.loads(path.read_text(encoding="utf-8")))


def write_animation(path: Path, value: dict[str, Any]) -> None:
    document = validate_animation(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json_text(document), encoding="utf-8")
