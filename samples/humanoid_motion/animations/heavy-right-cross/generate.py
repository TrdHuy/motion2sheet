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

ANIMATION_ID = "heavy-right-cross"
FPS = 8.0
FRAME_COUNT = 10
DURATION_SECONDS = (FRAME_COUNT - 1) / FPS
QUANTIZE_DIGITS = 12

# Character-A visual tuning pass: stronger stance/load, body-led drive, direct
# acceleration, committed impact, and staged recoil while preserving the locked
# Heavy Right Cross timing/Root contract and character-independent authority.

_POSES = [{'Hips': (-2, 0, -12), 'Spine': (2, 0, -8), 'Chest': (3, 0, -12), 'Neck': (0, 0, 6), 'Head': (0, 0, 3), 'LeftShoulder': (0, 0, -5), 'LeftUpperArm': (0, 42, -18), 'LeftLowerArm': (0, -132, -20), 'LeftHand': (0, -122, -16), 'RightShoulder': (0, 0, 4), 'RightUpperArm': (0, -42, 18), 'RightLowerArm': (0, 116, 20), 'RightHand': (0, 106, 18), 'LeftUpperLeg': (-16, -8, -5), 'LeftLowerLeg': (12, 6, 0), 'LeftFoot': (6, 4, -3), 'LeftToe': (0, 0, 0), 'RightUpperLeg': (14, 11, 6), 'RightLowerLeg': (-9, -7, 0), 'RightFoot': (-6, -5, 8), 'RightToe': (0, 0, 0)},
 {'Hips': (-3, 0, -18), 'Spine': (2, 0, -13), 'Chest': (3, 0, -17), 'Neck': (0, 0, 8), 'Head': (0, 0, 4), 'LeftShoulder': (0, 0, -5), 'LeftUpperArm': (0, 42, -18), 'LeftLowerArm': (0, -132, -20), 'LeftHand': (0, -122, -16), 'RightShoulder': (0, 0, 0), 'RightUpperArm': (0, -44, 16), 'RightLowerArm': (0, 120, 18), 'RightHand': (0, 110, 17), 'LeftUpperLeg': (-17, -8, -5), 'LeftLowerLeg': (13, 6, 0), 'LeftFoot': (6, 4, -3), 'LeftToe': (0, 0, 0), 'RightUpperLeg': (16, 12, 10), 'RightLowerLeg': (-9, -7, 0), 'RightFoot': (-7, -5, 14), 'RightToe': (0, 0, 0)},
 {'Hips': (-4, 0, -30), 'Spine': (1, 0, -22), 'Chest': (2, 0, -26), 'Neck': (0, 0, 11), 'Head': (0, 0, 6), 'LeftShoulder': (0, 0, -5), 'LeftUpperArm': (0, 42, -18), 'LeftLowerArm': (0, -132, -20), 'LeftHand': (0, -122, -16), 'RightShoulder': (0, 0, -7), 'RightUpperArm': (0, -46, 12), 'RightLowerArm': (0, 124, 16), 'RightHand': (0, 114, 16), 'LeftUpperLeg': (-19, -9, -6), 'LeftLowerLeg': (14, 7, 0), 'LeftFoot': (7, 4, -3), 'LeftToe': (0, 0, 0), 'RightUpperLeg': (18, 14, 16), 'RightLowerLeg': (-10, -8, 0), 'RightFoot': (-8, -6, 22), 'RightToe': (0, 0, 0)},
 {'Hips': (0, 0, -6), 'Spine': (3, 0, -15), 'Chest': (4, 0, -16), 'Neck': (0, 0, 7), 'Head': (0, 0, 4), 'LeftShoulder': (0, 0, -5), 'LeftUpperArm': (0, 42, -18), 'LeftLowerArm': (0, -132, -20), 'LeftHand': (0, -122, -16), 'RightShoulder': (0, 0, 8), 'RightUpperArm': (0, -42, 24), 'RightLowerArm': (0, 120, 25), 'RightHand': (0, 110, 21), 'LeftUpperLeg': (-18, -8, -5), 'LeftLowerLeg': (13, 6, 0), 'LeftFoot': (6, 4, -3), 'LeftToe': (0, 0, 0), 'RightUpperLeg': (17, 13, 24), 'RightLowerLeg': (-9, -7, 0), 'RightFoot': (-7, -5, 30), 'RightToe': (0, 0, 0)},
 {'Hips': (4, 0, 18), 'Spine': (6, 0, 10), 'Chest': (8, 0, 14), 'Neck': (-1, 0, -4), 'Head': (0, 0, -2), 'LeftShoulder': (0, 0, -6), 'LeftUpperArm': (0, 40, -20), 'LeftLowerArm': (0, -130, -22), 'LeftHand': (0, -120, -18), 'RightShoulder': (0, 0, 20), 'RightUpperArm': (0, -12, 72), 'RightLowerArm': (0, 20, 80), 'RightHand': (0, 12, 82), 'LeftUpperLeg': (-15, -6, -3), 'LeftLowerLeg': (11, 5, 0), 'LeftFoot': (5, 3, -2), 'LeftToe': (0, 0, 0), 'RightUpperLeg': (14, 10, 34), 'RightLowerLeg': (-7, -6, 0), 'RightFoot': (-5, -4, 42), 'RightToe': (0, 0, 0)},
 {'Hips': (8, 0, 34), 'Spine': (10, 0, 26), 'Chest': (12, 0, 40), 'Neck': (-3, 0, -14), 'Head': (1, 0, -8), 'LeftShoulder': (0, 0, -7), 'LeftUpperArm': (0, 39, -22), 'LeftLowerArm': (0, -129, -24), 'LeftHand': (0, -119, -20), 'RightShoulder': (0, 0, 34), 'RightUpperArm': (0, -4, 88), 'RightLowerArm': (0, -2, 90), 'RightHand': (0, 0, 90), 'LeftUpperLeg': (-13, -5, -2), 'LeftLowerLeg': (9, 4, 0), 'LeftFoot': (4, 2, -1), 'LeftToe': (0, 0, 0), 'RightUpperLeg': (12, 8, 42), 'RightLowerLeg': (-6, -5, 0), 'RightFoot': (-4, -3, 52), 'RightToe': (0, 0, 0)},
 {'Hips': (9, 0, 38), 'Spine': (11, 0, 30), 'Chest': (13, 0, 44), 'Neck': (-4, 0, -16), 'Head': (1, 0, -9), 'LeftShoulder': (0, 0, -7), 'LeftUpperArm': (0, 38, -22), 'LeftLowerArm': (0, -128, -24), 'LeftHand': (0, -118, -20), 'RightShoulder': (0, 0, 38), 'RightUpperArm': (0, -2, 94), 'RightLowerArm': (0, -4, 94), 'RightHand': (0, -2, 94), 'LeftUpperLeg': (-12, -4, -1), 'LeftLowerLeg': (8, 4, 0), 'LeftFoot': (4, 2, 0), 'LeftToe': (0, 0, 0), 'RightUpperLeg': (11, 7, 46), 'RightLowerLeg': (-5, -4, 0), 'RightFoot': (-3, -2, 56), 'RightToe': (0, 0, 0)},
 {'Hips': (5, 0, 18), 'Spine': (7, 0, 14), 'Chest': (8, 0, 18), 'Neck': (-1, 0, -5), 'Head': (0, 0, -2), 'LeftShoulder': (0, 0, -6), 'LeftUpperArm': (0, 40, -20), 'LeftLowerArm': (0, -130, -22), 'LeftHand': (0, -120, -18), 'RightShoulder': (0, 0, 18), 'RightUpperArm': (0, -22, 55), 'RightLowerArm': (0, 84, 58), 'RightHand': (0, 74, 50), 'LeftUpperLeg': (-14, -5, -2), 'LeftLowerLeg': (10, 5, 0), 'LeftFoot': (5, 3, -1), 'LeftToe': (0, 0, 0), 'RightUpperLeg': (13, 9, 30), 'RightLowerLeg': (-7, -6, 0), 'RightFoot': (-5, -4, 36), 'RightToe': (0, 0, 0)},
 {'Hips': (1, 0, 0), 'Spine': (3, 0, -2), 'Chest': (4, 0, -4), 'Neck': (0, 0, 3), 'Head': (0, 0, 1), 'LeftShoulder': (0, 0, -5), 'LeftUpperArm': (0, 41, -19), 'LeftLowerArm': (0, -131, -21), 'LeftHand': (0, -121, -17), 'RightShoulder': (0, 0, 8), 'RightUpperArm': (0, -36, 30), 'RightLowerArm': (0, 108, 32), 'RightHand': (0, 98, 26), 'LeftUpperLeg': (-15, -7, -4), 'LeftLowerLeg': (11, 6, 0), 'LeftFoot': (6, 4, -2), 'LeftToe': (0, 0, 0), 'RightUpperLeg': (15, 11, 14), 'RightLowerLeg': (-8, -7, 0), 'RightFoot': (-6, -5, 18), 'RightToe': (0, 0, 0)},
 {'Hips': (-1, 0, -10), 'Spine': (2, 0, -7), 'Chest': (3, 0, -10), 'Neck': (0, 0, 5), 'Head': (0, 0, 2), 'LeftShoulder': (0, 0, -5), 'LeftUpperArm': (0, 42, -18), 'LeftLowerArm': (0, -132, -20), 'LeftHand': (0, -122, -16), 'RightShoulder': (0, 0, 5), 'RightUpperArm': (0, -41, 20), 'RightLowerArm': (0, 116, 22), 'RightHand': (0, 106, 19), 'LeftUpperLeg': (-16, -8, -5), 'LeftLowerLeg': (12, 6, 0), 'LeftFoot': (6, 4, -3), 'LeftToe': (0, 0, 0), 'RightUpperLeg': (14, 11, 7), 'RightLowerLeg': (-9, -7, 0), 'RightFoot': (-6, -5, 9), 'RightToe': (0, 0, 0)}]

_HIPS_TRANSLATIONS = [(-0.015, 0.0, -0.015), (-0.008, 0.025, -0.028), (0.0, 0.05, -0.04), (0.005, 0.015, -0.035), (0.012, -0.025, -0.025), (0.015, -0.075, -0.018), (0.012, -0.082, -0.02), (0.004, -0.045, -0.026), (-0.006, -0.015, -0.02), (-0.015, 0.0, -0.015)]


def _clean(value: float) -> float:
    result = round(float(value), QUANTIZE_DIGITS)
    return 0.0 if result == 0.0 else result


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


def _rotation_track(semantic: str) -> list[list[float]]:
    track: list[list[float]] = []
    for pose in _POSES:
        quaternion = _euler_quaternion(pose.get(semantic, (0.0, 0.0, 0.0)))
        if track and sum(a * b for a, b in zip(track[-1], quaternion)) < 0.0:
            quaternion = [_clean(-component) for component in quaternion]
        if not track:
            first_nonzero = next((component for component in quaternion if abs(component) > 1e-15), 0.0)
            if first_nonzero < 0.0:
                quaternion = [_clean(-component) for component in quaternion]
        track.append(quaternion)
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
        "hips": {
            "translations": [[_clean(component) for component in value] for value in _HIPS_TRANSLATIONS],
            "rotations": _rotation_track("Hips"),
        },
        "joints": {
            semantic: {"rotations": _rotation_track(semantic)}
            for semantic in ROTATION_JOINTS
        },
    }


def write_compact_animation(path: Path) -> None:
    document = validate_animation(build_animation())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the locked Heavy Right Cross Humanoid Motion sample.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_compact_animation(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
