from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from motion2sheet.motion.humanoid_motion.schema import (
    ANIMATION_SCHEMA,
    CANONICAL_SKELETON_ID,
    EXPECTED_COORDINATE_SYSTEM,
    EXPECTED_QUATERNION_CONVENTION,
    ROTATION_JOINTS,
    validate_animation,
)

ANIMATION_ID = "right-overhand-smash"
FPS = 15.0
FRAME_COUNT = 15
DURATION_SECONDS = (FRAME_COUNT - 1) / FPS
KEY_FRAMES = (0, 2, 4, 6, 8, 10, 12, 14)
QUANTIZE_DIGITS = 12

_READY = {
    "Chest": (-4, 0, -6),
    "Head": (2, 0, 4),
    "Hips": (0, 0, -3),
    "LeftFoot": (2, 2, 0),
    "LeftHand": (0, -102, -8),
    "LeftLowerArm": (0, -112, -10),
    "LeftLowerLeg": (5, 4, 0),
    "LeftShoulder": (0, -8, -6),
    "LeftToe": (0, 0, 0),
    "LeftUpperArm": (0, -28, -10),
    "LeftUpperLeg": (-9, -6, 0),
    "Neck": (2, 0, 3),
    "RightFoot": (-2, -3, 0),
    "RightHand": (0, 92, 14),
    "RightLowerArm": (0, 100, 18),
    "RightLowerLeg": (-4, -5, 0),
    "RightShoulder": (0, 8, 8),
    "RightToe": (0, 0, 0),
    "RightUpperArm": (0, 22, 14),
    "RightUpperLeg": (8, 8, 0),
    "Spine": (-2, 0, -4),
}

_OVERRIDES = {
    2: {
        "Chest": (6, 0, 16), "Head": (-2, 0, -8), "Hips": (2, 0, 8),
        "LeftLowerArm": (0, -118, -16), "LeftUpperArm": (0, -34, -16), "LeftUpperLeg": (-11, -7, 0),
        "Neck": (-2, 0, -6), "RightHand": (0, 105, 20), "RightLowerArm": (-2, 118, 25),
        "RightShoulder": (0, 22, 18), "RightUpperArm": (-4, 48, 22), "RightUpperLeg": (10, 9, 0),
        "Spine": (4, 0, 12),
    },
    4: {
        "Chest": (10, 0, 27), "Head": (-4, 0, -14), "Hips": (4, 0, 17),
        "LeftLowerArm": (0, -120, -18), "LeftShoulder": (0, -14, -12), "LeftUpperArm": (0, -38, -20),
        "LeftUpperLeg": (-13, -8, 0), "Neck": (-4, 0, -11), "RightHand": (-4, 112, 24),
        "RightLowerArm": (-6, 128, 30), "RightShoulder": (-4, 34, 24), "RightUpperArm": (-8, 78, 30),
        "RightUpperLeg": (12, 10, 0), "Spine": (7, 0, 21),
    },
    6: {
        "Chest": (-10, 0, -1), "Head": (5, 0, 2), "Hips": (-3, 0, 4),
        "LeftLowerArm": (0, -118, -16), "LeftUpperArm": (0, -34, -16), "LeftUpperLeg": (-10, -5, 0),
        "Neck": (4, 0, 1), "RightHand": (-4, 38, 30), "RightLowerArm": (-6, 52, 34),
        "RightShoulder": (0, 12, 22), "RightUpperArm": (-8, 20, 30), "RightUpperLeg": (8, 6, 0),
        "Spine": (-7, 0, 2),
    },
    8: {
        "Chest": (-16, 0, -22), "Head": (8, 0, 12), "Hips": (-8, 0, -11),
        "LeftLowerArm": (0, -112, -20), "LeftShoulder": (0, -6, -18), "LeftUpperArm": (0, -30, -22),
        "LeftUpperLeg": (-8, -2, 0), "Neck": (7, 0, 9), "RightHand": (-6, -30, 34),
        "RightLowerArm": (-8, -38, 36), "RightLowerLeg": (-7, -5, 0), "RightShoulder": (2, -12, 24),
        "RightUpperArm": (-10, -48, 34), "RightUpperLeg": (5, 3, 0), "Spine": (-13, 0, -15),
    },
    10: {
        "Chest": (-20, 0, -29), "Head": (9, 0, 16), "Hips": (-10, 0, -15),
        "LeftLowerArm": (0, -108, -16), "LeftUpperArm": (0, -26, -18), "LeftUpperLeg": (-7, 0, 0),
        "Neck": (8, 0, 12), "RightHand": (-8, -48, 30), "RightLowerArm": (-10, -58, 32),
        "RightLowerLeg": (-8, -4, 0), "RightShoulder": (3, -24, 22), "RightUpperArm": (-12, -74, 30),
        "RightUpperLeg": (4, 1, 0), "Spine": (-16, 0, -21),
    },
    12: {
        "Chest": (-9, 0, -12), "Head": (4, 0, 7), "Hips": (-4, 0, -6),
        "LeftLowerArm": (0, -114, -14), "LeftUpperArm": (0, -30, -14), "Neck": (4, 0, 5),
        "RightHand": (-1, 58, 20), "RightLowerArm": (-2, 66, 24), "RightShoulder": (0, 0, 12),
        "RightUpperArm": (-3, 2, 20), "Spine": (-7, 0, -9),
    },
}

_HIPS_TRANSLATIONS = {
    0: (-0.015, 0.0, 0.0),
    2: (-0.005, 0.018, -0.015),
    4: (0.018, 0.028, -0.035),
    6: (0.035, 0.008, -0.045),
    8: (0.052, -0.018, -0.065),
    10: (0.045, -0.022, -0.055),
    12: (0.012, -0.008, -0.02),
    14: (-0.015, 0.0, 0.0),
}


def _clean(value: float) -> float:
    result = round(float(value), QUANTIZE_DIGITS)
    return 0.0 if result == 0.0 else result


def _pose(frame: int) -> dict[str, tuple[float, float, float]]:
    pose = dict(_READY)
    pose.update(_OVERRIDES.get(frame, {}))
    return pose


def _multiply(first: list[float], second: list[float]) -> list[float]:
    aw, ax, ay, az = first
    bw, bx, by, bz = second
    return [
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    ]


def _normalize(quaternion: list[float]) -> list[float]:
    norm = math.sqrt(sum(component * component for component in quaternion))
    if norm <= 0.0 or not math.isfinite(norm):
        raise ValueError("cannot normalize invalid quaternion")
    return [_clean(component / norm) for component in quaternion]


def _euler_quaternion(degrees_xyz: tuple[float, float, float]) -> list[float]:
    half_x, half_y, half_z = [math.radians(float(value)) * 0.5 for value in degrees_xyz]
    qx = [math.cos(half_x), math.sin(half_x), 0.0, 0.0]
    qy = [math.cos(half_y), 0.0, math.sin(half_y), 0.0]
    qz = [math.cos(half_z), 0.0, 0.0, math.sin(half_z)]
    return _normalize(_multiply(qz, _multiply(qy, qx)))


def _slerp(first: list[float], second: list[float], factor: float) -> list[float]:
    dot = sum(a * b for a, b in zip(first, second))
    target = list(second)
    if dot < 0.0:
        target = [-component for component in target]
        dot = -dot
    dot = max(-1.0, min(1.0, dot))
    if dot > 0.9995:
        return _normalize([(1.0 - factor) * a + factor * b for a, b in zip(first, target)])
    theta = math.acos(dot)
    sin_theta = math.sin(theta)
    return _normalize([
        math.sin((1.0 - factor) * theta) / sin_theta * a
        + math.sin(factor * theta) / sin_theta * b
        for a, b in zip(first, target)
    ])


def _rotation_track(semantic: str) -> list[list[float]]:
    keys = {frame: _euler_quaternion(_pose(frame).get(semantic, (0.0, 0.0, 0.0))) for frame in KEY_FRAMES}
    track: list[list[float]] = []
    for frame in range(FRAME_COUNT):
        if frame in keys:
            quaternion = list(keys[frame])
        else:
            lower = max(key for key in KEY_FRAMES if key < frame)
            upper = min(key for key in KEY_FRAMES if key > frame)
            quaternion = _slerp(keys[lower], keys[upper], (frame - lower) / (upper - lower))
        if track and sum(a * b for a, b in zip(track[-1], quaternion)) < 0.0:
            quaternion = [_clean(-component) for component in quaternion]
        if not track:
            first_nonzero = next((component for component in quaternion if abs(component) > 1e-15), 0.0)
            if first_nonzero < 0.0:
                quaternion = [_clean(-component) for component in quaternion]
        track.append(quaternion)
    return track


def _translation_track() -> list[list[float]]:
    track: list[list[float]] = []
    for frame in range(FRAME_COUNT):
        if frame in _HIPS_TRANSLATIONS:
            value = _HIPS_TRANSLATIONS[frame]
        else:
            lower = max(key for key in KEY_FRAMES if key < frame)
            upper = min(key for key in KEY_FRAMES if key > frame)
            factor = (frame - lower) / (upper - lower)
            value = tuple(
                (1.0 - factor) * _HIPS_TRANSLATIONS[lower][axis]
                + factor * _HIPS_TRANSLATIONS[upper][axis]
                for axis in range(3)
            )
        track.append([_clean(component) for component in value])
    return track


def build_animation() -> dict:
    identity = [1.0, 0.0, 0.0, 0.0]
    return {
        "schema": ANIMATION_SCHEMA,
        "version": 1,
        "id": ANIMATION_ID,
        "canonicalSkeleton": CANONICAL_SKELETON_ID,
        "durationSeconds": DURATION_SECONDS,
        "fps": FPS,
        "frameCount": FRAME_COUNT,
        "loop": False,
        "coordinateSystem": dict(EXPECTED_COORDINATE_SYSTEM),
        "quaternionConvention": dict(EXPECTED_QUATERNION_CONVENTION),
        "root": {
            "translations": [[0.0, 0.0, 0.0] for _ in range(FRAME_COUNT)],
            "rotations": [identity[:] for _ in range(FRAME_COUNT)],
        },
        "hips": {"translations": _translation_track(), "rotations": _rotation_track("Hips")},
        "joints": {semantic: {"rotations": _rotation_track(semantic)} for semantic in ROTATION_JOINTS},
    }


def write_compact_animation(path: Path) -> None:
    document = validate_animation(build_animation())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the direct-authored Right Overhand Smash Humanoid Motion sample.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_compact_animation(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
