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

# Character-A visual tuning pass 4:
# keep F4 visibly loaded, make F5 the first full extension, increase torso lean
# and forward weight transfer, then fold the right arm back into guard at F7.
# The reusable Humanoid authority, 10@8 timing, F5 impact and zero Root contract stay locked.

_POSES = [{'Hips': (-3, 0, -14),
  'Spine': (2, 0, -9),
  'Chest': (3, 0, -13),
  'Neck': (0, 0, 5),
  'Head': (0, 0, 2),
  'LeftShoulder': (0, 0, -5),
  'LeftUpperArm': (0, 42, -18),
  'LeftLowerArm': (0, -132, -20),
  'LeftHand': (-35, -122, -16),
  'RightShoulder': (0, 0, 4),
  'RightUpperArm': (0, -42, 18),
  'RightLowerArm': (0, 116, 20),
  'RightHand': (-45, 106, 18),
  'LeftUpperLeg': (-16, -8, -5),
  'LeftLowerLeg': (12, 6, 0),
  'LeftFoot': (6, 4, -3),
  'LeftToe': (0, 0, 0),
  'RightUpperLeg': (14, 11, 6),
  'RightLowerLeg': (-9, -7, 0),
  'RightFoot': (-6, -5, 8),
  'RightToe': (0, 0, 0)},
 {'Hips': (-5, 0, -24),
  'Spine': (3, 0, -18),
  'Chest': (4, 0, -22),
  'Neck': (0, 0, 9),
  'Head': (0, 0, 4),
  'LeftShoulder': (0, 0, -5),
  'LeftUpperArm': (0, 42, -18),
  'LeftLowerArm': (0, -132, -20),
  'LeftHand': (-35, -122, -16),
  'RightShoulder': (0, 0, -2),
  'RightUpperArm': (0, -44, 14),
  'RightLowerArm': (0, 121, 18),
  'RightHand': (-48, 111, 17),
  'LeftUpperLeg': (-18, -8, -5),
  'LeftLowerLeg': (13, 6, 0),
  'LeftFoot': (6, 4, -3),
  'LeftToe': (0, 0, 0),
  'RightUpperLeg': (17, 12, 11),
  'RightLowerLeg': (-9, -7, 0),
  'RightFoot': (-7, -5, 18),
  'RightToe': (0, 0, 0)},
 {'Hips': (-10, 0, -40),
  'Spine': (2, 0, -30),
  'Chest': (3, 0, -36),
  'Neck': (0, 0, 14),
  'Head': (0, 0, 8),
  'LeftShoulder': (0, 0, -5),
  'LeftUpperArm': (0, 42, -18),
  'LeftLowerArm': (0, -132, -20),
  'LeftHand': (-35, -122, -16),
  'RightShoulder': (0, 0, -12),
  'RightUpperArm': (0, -48, 8),
  'RightLowerArm': (0, 126, 14),
  'RightHand': (-50, 116, 14),
  'LeftUpperLeg': (-20, -9, -6),
  'LeftLowerLeg': (15, 7, 0),
  'LeftFoot': (7, 4, -3),
  'LeftToe': (0, 0, 0),
  'RightUpperLeg': (20, 14, 18),
  'RightLowerLeg': (-10, -8, 0),
  'RightFoot': (-8, -6, 28),
  'RightToe': (0, 0, 0)},
 {'Hips': (4, 0, -4),
  'Spine': (6, 0, -17),
  'Chest': (7, 0, -20),
  'Neck': (0, 0, 8),
  'Head': (0, 0, 4),
  'LeftShoulder': (0, 0, -5),
  'LeftUpperArm': (0, 42, -18),
  'LeftLowerArm': (0, -132, -20),
  'LeftHand': (-35, -122, -16),
  'RightShoulder': (0, 0, 8),
  'RightUpperArm': (0, -42, 24),
  'RightLowerArm': (0, 120, 24),
  'RightHand': (-48, 110, 20),
  'LeftUpperLeg': (-18, -8, -5),
  'LeftLowerLeg': (13, 6, 0),
  'LeftFoot': (6, 4, -3),
  'LeftToe': (0, 0, 0),
  'RightUpperLeg': (18, 13, 27),
  'RightLowerLeg': (-9, -7, 0),
  'RightFoot': (-7, -5, 38),
  'RightToe': (0, 0, 0)},
 {'Hips': (14, 0, 22),
  'Spine': (16, 0, 14),
  'Chest': (18, 0, 20),
  'Neck': (-6, 0, -4),
  'Head': (-3, 0, -2),
  'LeftShoulder': (0, 0, -6),
  'LeftUpperArm': (0, 40, -20),
  'LeftLowerArm': (0, -130, -22),
  'LeftHand': (-38, -120, -18),
  'RightShoulder': (0, 0, 30),
  'RightUpperArm': (0, -25, 60),
  'RightLowerArm': (0, 50, 70),
  'RightHand': (-75, 8, 84),
  'LeftUpperLeg': (-15, -6, -3),
  'LeftLowerLeg': (11, 5, 0),
  'LeftFoot': (5, 3, -2),
  'LeftToe': (0, 0, 0),
  'RightUpperLeg': (15, 10, 38),
  'RightLowerLeg': (-7, -6, 0),
  'RightFoot': (-5, -4, 54),
  'RightToe': (0, 0, 0)},
 {'Hips': (26, 0, 40),
  'Spine': (22, 0, 32),
  'Chest': (18, 0, 46),
  'Neck': (-15, 0, -18),
  'Head': (-8, 0, -10),
  'LeftShoulder': (0, 0, -7),
  'LeftUpperArm': (0, 39, -22),
  'LeftLowerArm': (0, -129, -24),
  'LeftHand': (-40, -119, -20),
  'RightShoulder': (0, 0, 42),
  'RightUpperArm': (0, -2, 89),
  'RightLowerArm': (0, -2, 90),
  'RightHand': (-85, 0, 90),
  'LeftUpperLeg': (-13, -5, -2),
  'LeftLowerLeg': (9, 4, 0),
  'LeftFoot': (4, 2, -1),
  'LeftToe': (0, 0, 0),
  'RightUpperLeg': (12, 8, 46),
  'RightLowerLeg': (-6, -5, 0),
  'RightFoot': (-4, -3, 66),
  'RightToe': (0, 0, 0)},
 {'Hips': (28, 0, 44),
  'Spine': (24, 0, 36),
  'Chest': (18, 0, 50),
  'Neck': (-16, 0, -20),
  'Head': (-8, 0, -11),
  'LeftShoulder': (0, 0, -7),
  'LeftUpperArm': (0, 38, -22),
  'LeftLowerArm': (0, -128, -24),
  'LeftHand': (-40, -118, -20),
  'RightShoulder': (0, 0, 46),
  'RightUpperArm': (0, 2, 95),
  'RightLowerArm': (0, -5, 96),
  'RightHand': (-80, -2, 96),
  'LeftUpperLeg': (-12, -4, -1),
  'LeftLowerLeg': (8, 4, 0),
  'LeftFoot': (4, 2, 0),
  'LeftToe': (0, 0, 0),
  'RightUpperLeg': (11, 7, 50),
  'RightLowerLeg': (-5, -4, 0),
  'RightFoot': (-3, -2, 70),
  'RightToe': (0, 0, 0)},
 {'Hips': (16, 0, 24),
  'Spine': (14, 0, 18),
  'Chest': (12, 0, 24),
  'Neck': (-6, 0, -8),
  'Head': (-3, 0, -4),
  'LeftShoulder': (0, 0, -6),
  'LeftUpperArm': (0, 40, -22),
  'LeftLowerArm': (0, -130, -22),
  'LeftHand': (-38, -120, -18),
  'RightShoulder': (0, 0, 18),
  'RightUpperArm': (0, -32, 38),
  'RightLowerArm': (0, 108, 28),
  'RightHand': (-60, 98, 20),
  'LeftUpperLeg': (-14, -5, -2),
  'LeftLowerLeg': (10, 5, 0),
  'LeftFoot': (5, 3, -1),
  'LeftToe': (0, 0, 0),
  'RightUpperLeg': (13, 9, 32),
  'RightLowerLeg': (-7, -6, 0),
  'RightFoot': (-5, -4, 44),
  'RightToe': (0, 0, 0)},
 {'Hips': (3, 0, 2),
  'Spine': (5, 0, -2),
  'Chest': (6, 0, -4),
  'Neck': (0, 0, 3),
  'Head': (0, 0, 1),
  'LeftShoulder': (0, 0, -5),
  'LeftUpperArm': (0, 41, -19),
  'LeftLowerArm': (0, -131, -21),
  'LeftHand': (-35, -121, -17),
  'RightShoulder': (0, 0, 10),
  'RightUpperArm': (0, -35, 30),
  'RightLowerArm': (0, 112, 30),
  'RightHand': (-42, 102, 24),
  'LeftUpperLeg': (-15, -7, -4),
  'LeftLowerLeg': (11, 6, 0),
  'LeftFoot': (6, 4, -2),
  'LeftToe': (0, 0, 0),
  'RightUpperLeg': (15, 11, 15),
  'RightLowerLeg': (-8, -7, 0),
  'RightFoot': (-6, -5, 22),
  'RightToe': (0, 0, 0)},
 {'Hips': (-2, 0, -11),
  'Spine': (2, 0, -8),
  'Chest': (3, 0, -11),
  'Neck': (0, 0, 5),
  'Head': (0, 0, 2),
  'LeftShoulder': (0, 0, -5),
  'LeftUpperArm': (0, 42, -18),
  'LeftLowerArm': (0, -132, -20),
  'LeftHand': (-35, -122, -16),
  'RightShoulder': (0, 0, 5),
  'RightUpperArm': (0, -41, 20),
  'RightLowerArm': (0, 116, 22),
  'RightHand': (-45, 106, 19),
  'LeftUpperLeg': (-16, -8, -5),
  'LeftLowerLeg': (12, 6, 0),
  'LeftFoot': (6, 4, -3),
  'LeftToe': (0, 0, 0),
  'RightUpperLeg': (14, 11, 7),
  'RightLowerLeg': (-9, -7, 0),
  'RightFoot': (-6, -5, 10),
  'RightToe': (0, 0, 0)}]

_HIPS_TRANSLATIONS = [(-0.015, 0, -0.03),
 (-0.008, 0.04, -0.05),
 (0, 0.08, -0.08),
 (0.008, 0.04, -0.07),
 (0.015, -0.08, -0.06),
 (0.02, -0.19, -0.055),
 (0.018, -0.21, -0.05),
 (0.008, -0.11, -0.055),
 (-0.004, -0.035, -0.04),
 (-0.015, 0, -0.03)]


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
