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

# Mechanics tuning pass 6: preserve the locked Heavy Right Cross while reducing
# local pelvis travel and torso overtwist, keeping a slight F5 elbow bend,
# aligning the wrist with the forearm, making F6 a small overshoot, and
# distributing recoil across F7-F9.
_POSES = json.loads(r'''[{"Hips":[-3,0,-12],"Spine":[2,0,-7],"Chest":[3,0,-10],"Neck":[0,0,4],"Head":[0,0,2],"LeftShoulder":[0,0,-5],"LeftUpperArm":[0,42,-18],"LeftLowerArm":[0,-132,-20],"LeftHand":[-35,-122,-16],"RightShoulder":[0,0,4],"RightUpperArm":[0,-42,18],"RightLowerArm":[0,116,20],"RightHand":[-10,108,20],"LeftUpperLeg":[-20,-8,-5],"LeftLowerLeg":[12,6,0],"LeftFoot":[6,4,-3],"LeftToe":[0,0,0],"RightUpperLeg":[16,11,6],"RightLowerLeg":[-9,-7,0],"RightFoot":[-6,-5,8],"RightToe":[0,0,0]},{"Hips":[-4,0,-20],"Spine":[2,0,-12],"Chest":[3,0,-16],"Neck":[0,0,7],"Head":[0,0,4],"LeftShoulder":[0,0,-5],"LeftUpperArm":[0,42,-18],"LeftLowerArm":[0,-132,-20],"LeftHand":[-35,-122,-16],"RightShoulder":[0,0,0],"RightUpperArm":[0,-44,14],"RightLowerArm":[0,121,18],"RightHand":[-10,113,18],"LeftUpperLeg":[-21,-8,-5],"LeftLowerLeg":[13,6,0],"LeftFoot":[6,4,-3],"LeftToe":[0,0,0],"RightUpperLeg":[18,12,10],"RightLowerLeg":[-9,-7,0],"RightFoot":[-7,-5,14],"RightToe":[0,0,0]},{"Hips":[-6,0,-30],"Spine":[1,0,-18],"Chest":[2,0,-22],"Neck":[0,0,10],"Head":[0,0,6],"LeftShoulder":[0,0,-5],"LeftUpperArm":[0,42,-18],"LeftLowerArm":[0,-132,-20],"LeftHand":[-35,-122,-16],"RightShoulder":[0,0,-8],"RightUpperArm":[0,-47,10],"RightLowerArm":[0,124,14],"RightHand":[-10,116,15],"LeftUpperLeg":[-23,-9,-6],"LeftLowerLeg":[14,7,0],"LeftFoot":[7,4,-3],"LeftToe":[0,0,0],"RightUpperLeg":[21,13,15],"RightLowerLeg":[-10,-8,0],"RightFoot":[-8,-6,22],"RightToe":[0,0,0]},{"Hips":[1,0,-8],"Spine":[4,0,-14],"Chest":[5,0,-16],"Neck":[0,0,7],"Head":[0,0,4],"LeftShoulder":[0,0,-5],"LeftUpperArm":[0,42,-18],"LeftLowerArm":[0,-132,-20],"LeftHand":[-35,-122,-16],"RightShoulder":[0,0,6],"RightUpperArm":[0,-42,22],"RightLowerArm":[0,118,22],"RightHand":[-10,110,22],"LeftUpperLeg":[-22,-8,-5],"LeftLowerLeg":[13,6,0],"LeftFoot":[6,4,-3],"LeftToe":[0,0,0],"RightUpperLeg":[20,12,22],"RightLowerLeg":[-9,-7,0],"RightFoot":[-7,-5,30],"RightToe":[0,0,0]},{"Hips":[6,0,12],"Spine":[7,0,2],"Chest":[8,0,6],"Neck":[-2,0,-1],"Head":[-1,0,0],"LeftShoulder":[0,0,-6],"LeftUpperArm":[0,41,-19],"LeftLowerArm":[0,-131,-21],"LeftHand":[-36,-121,-17],"RightShoulder":[0,0,22],"RightUpperArm":[0,-24,58],"RightLowerArm":[0,48,66],"RightHand":[-8,52,64],"LeftUpperLeg":[-19,-7,-4],"LeftLowerLeg":[12,5,0],"LeftFoot":[5,3,-2],"LeftToe":[0,0,0],"RightUpperLeg":[18,10,30],"RightLowerLeg":[-8,-6,0],"RightFoot":[-6,-4,40],"RightToe":[0,0,0]},{"Hips":[10,0,26],"Spine":[8,0,9],"Chest":[9,0,12],"Neck":[-5,0,-8],"Head":[-3,0,-4],"LeftShoulder":[0,0,-6],"LeftUpperArm":[0,40,-20],"LeftLowerArm":[0,-130,-22],"LeftHand":[-37,-120,-18],"RightShoulder":[0,0,34],"RightUpperArm":[0,-4,84],"RightLowerArm":[0,0,79],"RightHand":[-6,4,81],"LeftUpperLeg":[-17,-6,-3],"LeftLowerLeg":[10,5,0],"LeftFoot":[5,3,-2],"LeftToe":[0,0,0],"RightUpperLeg":[16,8,36],"RightLowerLeg":[-7,-5,0],"RightFoot":[-5,-3,48],"RightToe":[0,0,0]},{"Hips":[11,0,28],"Spine":[9,0,10],"Chest":[10,0,13],"Neck":[-6,0,-9],"Head":[-3,0,-5],"LeftShoulder":[0,0,-6],"LeftUpperArm":[0,40,-20],"LeftLowerArm":[0,-130,-22],"LeftHand":[-37,-120,-18],"RightShoulder":[0,0,35],"RightUpperArm":[0,-3,82],"RightLowerArm":[0,2,77],"RightHand":[-6,6,79],"LeftUpperLeg":[-16,-5,-2],"LeftLowerLeg":[9,4,0],"LeftFoot":[4,2,-1],"LeftToe":[0,0,0],"RightUpperLeg":[15,7,38],"RightLowerLeg":[-6,-5,0],"RightFoot":[-4,-3,50],"RightToe":[0,0,0]},{"Hips":[9,0,22],"Spine":[8,0,7],"Chest":[9,0,9],"Neck":[-4,0,-5],"Head":[-2,0,-3],"LeftShoulder":[0,0,-6],"LeftUpperArm":[0,40,-20],"LeftLowerArm":[0,-130,-22],"LeftHand":[-37,-120,-18],"RightShoulder":[0,0,29],"RightUpperArm":[0,-12,66],"RightLowerArm":[0,40,58],"RightHand":[-7,40,60],"LeftUpperLeg":[-18,-6,-3],"LeftLowerLeg":[10,5,0],"LeftFoot":[5,3,-2],"LeftToe":[0,0,0],"RightUpperLeg":[16,8,32],"RightLowerLeg":[-7,-6,0],"RightFoot":[-5,-4,41],"RightToe":[0,0,0]},{"Hips":[4,0,7],"Spine":[5,0,0],"Chest":[6,0,0],"Neck":[-1,0,0],"Head":[-1,0,0],"LeftShoulder":[0,0,-5],"LeftUpperArm":[0,41,-19],"LeftLowerArm":[0,-131,-21],"LeftHand":[-35,-121,-17],"RightShoulder":[0,0,17],"RightUpperArm":[0,-26,44],"RightLowerArm":[0,78,40],"RightHand":[-9,78,40],"LeftUpperLeg":[-19,-7,-4],"LeftLowerLeg":[11,6,0],"LeftFoot":[6,4,-2],"LeftToe":[0,0,0],"RightUpperLeg":[18,10,19],"RightLowerLeg":[-8,-7,0],"RightFoot":[-6,-5,25],"RightToe":[0,0,0]},{"Hips":[-2,0,-10],"Spine":[2,0,-7],"Chest":[3,0,-9],"Neck":[0,0,4],"Head":[0,0,2],"LeftShoulder":[0,0,-5],"LeftUpperArm":[0,42,-18],"LeftLowerArm":[0,-132,-20],"LeftHand":[-35,-122,-16],"RightShoulder":[0,0,5],"RightUpperArm":[0,-40,22],"RightLowerArm":[0,114,22],"RightHand":[-10,106,22],"LeftUpperLeg":[-20,-8,-5],"LeftLowerLeg":[12,6,0],"LeftFoot":[6,4,-3],"LeftToe":[0,0,0],"RightUpperLeg":[16,11,8],"RightLowerLeg":[-9,-7,0],"RightFoot":[-6,-5,10],"RightToe":[0,0,0]}]''')
_HIPS_TRANSLATIONS = json.loads(r'''[[-0.01,0,-0.04],[-0.006,0.03,-0.05],[0,0.06,-0.065],[0.004,0.035,-0.06],[0.008,-0.025,-0.058],[0.01,-0.08,-0.055],[0.009,-0.085,-0.053],[0.004,-0.055,-0.052],[-0.003,-0.025,-0.045],[-0.01,0,-0.04]]''')


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
    values: list[list[float]] = []
    for pose in _POSES:
        quaternion = _euler_quaternion(tuple(pose.get(semantic, (0.0, 0.0, 0.0))))
        if values and sum(a * b for a, b in zip(values[-1], quaternion)) < 0.0:
            quaternion = [_clean(-component) for component in quaternion]
        if not values:
            first_nonzero = next((component for component in quaternion if abs(component) > 1e-15), 0.0)
            if first_nonzero < 0.0:
                quaternion = [_clean(-component) for component in quaternion]
        values.append(quaternion)
    return values


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
    parser = argparse.ArgumentParser(description="Generate the locked Heavy Right Cross Humanoid Motion sample.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_compact_animation(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
