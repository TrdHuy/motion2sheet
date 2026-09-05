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
FPS = 8.0
FRAME_COUNT = 8
DURATION_SECONDS = (FRAME_COUNT - 1) / FPS
QUANTIZE_DIGITS = 12

# Eight canonical semantic key poses. The left arm stays a compact guard while
# the physical right arm goes ready -> high wind-up -> downward impact ->
# follow-through -> recovery. These are canonical-scene deltas, not target
# character bone rotations.
_POSES = (
    {
        "Hips": (0, 0, -3),
        "Spine": (-2, 0, -4),
        "Chest": (-4, 0, -6),
        "Neck": (2, 0, 3),
        "Head": (2, 0, 4),
        "LeftShoulder": (0, 0, -6),
        "LeftUpperArm": (0, 45, -10),
        "LeftLowerArm": (0, -135, -10),
        "LeftHand": (0, -125, -8),
        "RightShoulder": (0, 0, 8),
        "RightUpperArm": (0, -45, 14),
        "RightLowerArm": (0, 135, 18),
        "RightHand": (0, 125, 14),
        "LeftUpperLeg": (-9, -6, 0),
        "LeftLowerLeg": (5, 4, 0),
        "LeftFoot": (2, 2, 0),
        "LeftToe": (0, 0, 0),
        "RightUpperLeg": (8, 8, 0),
        "RightLowerLeg": (-4, -5, 0),
        "RightFoot": (-2, -3, 0),
        "RightToe": (0, 0, 0),
    },
    {
        "Hips": (2, 0, 8),
        "Spine": (4, 0, 12),
        "Chest": (6, 0, 16),
        "Neck": (-2, 0, -6),
        "Head": (-2, 0, -8),
        "LeftShoulder": (0, 0, -8),
        "LeftUpperArm": (0, 45, -12),
        "LeftLowerArm": (0, -135, -12),
        "LeftHand": (0, -125, -10),
        "RightShoulder": (0, 22, 18),
        "RightUpperArm": (-4, 48, 22),
        "RightLowerArm": (-2, 118, 25),
        "RightHand": (0, 105, 20),
        "LeftUpperLeg": (-11, -7, 0),
        "LeftLowerLeg": (5, 4, 0),
        "LeftFoot": (2, 2, 0),
        "LeftToe": (0, 0, 0),
        "RightUpperLeg": (10, 9, 0),
        "RightLowerLeg": (-4, -5, 0),
        "RightFoot": (-2, -3, 0),
        "RightToe": (0, 0, 0),
    },
    {
        "Hips": (4, 0, 17),
        "Spine": (7, 0, 21),
        "Chest": (10, 0, 27),
        "Neck": (-4, 0, -11),
        "Head": (-4, 0, -14),
        "LeftShoulder": (0, 0, -10),
        "LeftUpperArm": (0, 45, -14),
        "LeftLowerArm": (0, -135, -14),
        "LeftHand": (0, -125, -10),
        "RightShoulder": (-4, 34, 24),
        "RightUpperArm": (-8, 78, 30),
        "RightLowerArm": (-6, 128, 30),
        "RightHand": (-4, 112, 24),
        "LeftUpperLeg": (-13, -8, 0),
        "LeftLowerLeg": (5, 4, 0),
        "LeftFoot": (2, 2, 0),
        "LeftToe": (0, 0, 0),
        "RightUpperLeg": (12, 10, 0),
        "RightLowerLeg": (-4, -5, 0),
        "RightFoot": (-2, -3, 0),
        "RightToe": (0, 0, 0),
    },
    {
        "Hips": (-3, 0, 4),
        "Spine": (-7, 0, 2),
        "Chest": (-10, 0, -1),
        "Neck": (4, 0, 1),
        "Head": (5, 0, 2),
        "LeftShoulder": (0, 0, -10),
        "LeftUpperArm": (0, 45, -14),
        "LeftLowerArm": (0, -135, -14),
        "LeftHand": (0, -125, -10),
        "RightShoulder": (0, 12, 22),
        "RightUpperArm": (-8, 20, 30),
        "RightLowerArm": (-6, 52, 34),
        "RightHand": (-4, 38, 30),
        "LeftUpperLeg": (-10, -5, 0),
        "LeftLowerLeg": (5, 4, 0),
        "LeftFoot": (2, 2, 0),
        "LeftToe": (0, 0, 0),
        "RightUpperLeg": (8, 6, 0),
        "RightLowerLeg": (-4, -5, 0),
        "RightFoot": (-2, -3, 0),
        "RightToe": (0, 0, 0),
    },
    {
        "Hips": (-8, 0, -11),
        "Spine": (-13, 0, -15),
        "Chest": (-16, 0, -22),
        "Neck": (7, 0, 9),
        "Head": (8, 0, 12),
        "LeftShoulder": (0, 0, -12),
        "LeftUpperArm": (0, 45, -16),
        "LeftLowerArm": (0, -135, -16),
        "LeftHand": (0, -125, -12),
        "RightShoulder": (2, -12, 24),
        "RightUpperArm": (-10, -48, 34),
        "RightLowerArm": (-8, -38, 36),
        "RightHand": (-6, -30, 34),
        "LeftUpperLeg": (-8, -2, 0),
        "LeftLowerLeg": (5, 4, 0),
        "LeftFoot": (2, 2, 0),
        "LeftToe": (0, 0, 0),
        "RightUpperLeg": (5, 3, 0),
        "RightLowerLeg": (-7, -5, 0),
        "RightFoot": (-2, -3, 0),
        "RightToe": (0, 0, 0),
    },
    {
        "Hips": (-10, 0, -15),
        "Spine": (-16, 0, -21),
        "Chest": (-20, 0, -29),
        "Neck": (8, 0, 12),
        "Head": (9, 0, 16),
        "LeftShoulder": (0, 0, -12),
        "LeftUpperArm": (0, 45, -16),
        "LeftLowerArm": (0, -135, -16),
        "LeftHand": (0, -125, -12),
        "RightShoulder": (3, -24, 22),
        "RightUpperArm": (-12, -74, 30),
        "RightLowerArm": (-10, -58, 32),
        "RightHand": (-8, -48, 30),
        "LeftUpperLeg": (-7, 0, 0),
        "LeftLowerLeg": (5, 4, 0),
        "LeftFoot": (2, 2, 0),
        "LeftToe": (0, 0, 0),
        "RightUpperLeg": (4, 1, 0),
        "RightLowerLeg": (-8, -4, 0),
        "RightFoot": (-2, -3, 0),
        "RightToe": (0, 0, 0),
    },
    {
        "Hips": (-4, 0, -6),
        "Spine": (-7, 0, -9),
        "Chest": (-9, 0, -12),
        "Neck": (4, 0, 5),
        "Head": (4, 0, 7),
        "LeftShoulder": (0, 0, -8),
        "LeftUpperArm": (0, 45, -12),
        "LeftLowerArm": (0, -135, -12),
        "LeftHand": (0, -125, -10),
        "RightShoulder": (0, 0, 12),
        "RightUpperArm": (-3, -35, 20),
        "RightLowerArm": (-2, 125, 24),
        "RightHand": (-1, 115, 20),
        "LeftUpperLeg": (-9, -6, 0),
        "LeftLowerLeg": (5, 4, 0),
        "LeftFoot": (2, 2, 0),
        "LeftToe": (0, 0, 0),
        "RightUpperLeg": (8, 8, 0),
        "RightLowerLeg": (-4, -5, 0),
        "RightFoot": (-2, -3, 0),
        "RightToe": (0, 0, 0),
    },
    {
        "Hips": (0, 0, -3),
        "Spine": (-2, 0, -4),
        "Chest": (-4, 0, -6),
        "Neck": (2, 0, 3),
        "Head": (2, 0, 4),
        "LeftShoulder": (0, 0, -6),
        "LeftUpperArm": (0, 45, -10),
        "LeftLowerArm": (0, -135, -10),
        "LeftHand": (0, -125, -8),
        "RightShoulder": (0, 0, 8),
        "RightUpperArm": (0, -45, 14),
        "RightLowerArm": (0, 135, 18),
        "RightHand": (0, 125, 14),
        "LeftUpperLeg": (-9, -6, 0),
        "LeftLowerLeg": (5, 4, 0),
        "LeftFoot": (2, 2, 0),
        "LeftToe": (0, 0, 0),
        "RightUpperLeg": (8, 8, 0),
        "RightLowerLeg": (-4, -5, 0),
        "RightFoot": (-2, -3, 0),
        "RightToe": (0, 0, 0),
    },
)

_HIPS_TRANSLATIONS = (
    (-0.015, 0.0, 0.0),
    (-0.005, 0.018, -0.015),
    (0.018, 0.028, -0.035),
    (0.035, 0.008, -0.045),
    (0.052, -0.018, -0.065),
    (0.045, -0.022, -0.055),
    (0.012, -0.008, -0.02),
    (-0.015, 0.0, 0.0),
)


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
    parser = argparse.ArgumentParser(
        description="Generate the direct-authored Right Overhand Smash Humanoid Motion sample."
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_compact_animation(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
