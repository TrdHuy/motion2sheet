from __future__ import annotations

import math
from typing import Iterable

from mathutils import Matrix, Quaternion, Vector


def clean_float(value: float) -> float:
    result = float(value)
    return 0.0 if abs(result) < 1e-15 else result


def quaternion_values(value: Quaternion) -> list[float]:
    components = [float(value.w), float(value.x), float(value.y), float(value.z)]
    norm = math.sqrt(sum(component * component for component in components))
    if norm <= 1e-15:
        raise RuntimeError("Contract C quaternion cannot be zero")
    return [clean_float(component / norm) for component in components]


def continuous_quaternion_values(values: Iterable[Quaternion]) -> list[list[float]]:
    result: list[list[float]] = []
    previous: Quaternion | None = None
    for raw in values:
        value = raw.normalized()
        components = [float(value.w), float(value.x), float(value.y), float(value.z)]
        if previous is None:
            first = next((component for component in components if abs(component) > 1e-15), 0.0)
            flip = first < 0.0
        else:
            dot = float(previous.dot(value))
            if abs(dot) <= 1e-12:
                first = next((component for component in components if abs(component) > 1e-15), 0.0)
                flip = first < 0.0
            else:
                flip = dot < 0.0
        if flip:
            value = Quaternion((-value.w, -value.x, -value.y, -value.z))
        result.append(quaternion_values(value))
        previous = value
    return result


def vector_values(value: Vector) -> list[float]:
    return [clean_float(value[index]) for index in range(3)]


def world_rest_matrix(armature, bone_name: str) -> Matrix:
    return armature.matrix_world @ armature.data.bones[bone_name].matrix_local


def world_pose_matrix(armature, bone_name: str) -> Matrix:
    return armature.matrix_world @ armature.pose.bones[bone_name].matrix


def mean_leg_length(armature, joints: dict[str, str]) -> float:
    totals = []
    for side in ("Left", "Right"):
        total = 0.0
        for semantic in (f"{side}UpperLeg", f"{side}LowerLeg"):
            bone = armature.data.bones[joints[semantic]]
            head = armature.matrix_world @ bone.head_local
            tail = armature.matrix_world @ bone.tail_local
            total += (tail - head).length
        totals.append(total)
    result = sum(totals) / len(totals)
    if not math.isfinite(result) or result <= 1e-8:
        raise RuntimeError(f"Contract C mean leg length must be positive and finite; got {result}")
    return float(result)


def yaw_twist(value: Quaternion) -> Quaternion:
    value = value.normalized()
    twist = Quaternion((float(value.w), 0.0, 0.0, float(value.z)))
    if twist.magnitude <= 1e-12:
        return Quaternion((1.0, 0.0, 0.0, 0.0))
    twist.normalize()
    return twist


def rotation_error_degrees(first: Quaternion, second: Quaternion) -> float:
    angle = float(first.normalized().rotation_difference(second.normalized()).angle)
    # q and -q encode the same rotation; fold mathutils' possible long arc.
    return math.degrees(min(angle, abs(2.0 * math.pi - angle)))
