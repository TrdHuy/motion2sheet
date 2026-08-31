"""Exact deterministic humanoid arm-segment FK helpers."""
from __future__ import annotations

import bpy
from mathutils import Matrix, Vector

from .humanoid import bone_head_world, bone_tail_world

ARM_IK_BONES = ("LeftForeArm", "RightForeArm")
ARM_SEGMENTS = {
    "left": ("LeftUpperArm", "LeftForeArm", "LeftHand"),
    "right": ("RightUpperArm", "RightForeArm", "RightHand"),
}


def disable_arm_ik(arm) -> None:
    for bone_name in ARM_IK_BONES:
        constraint = arm.pose.bones[bone_name].constraints.get(f"ReferenceIK_{bone_name}")
        if constraint is None:
            raise RuntimeError(f"missing arm IK constraint on {bone_name}")
        constraint.influence = 0.0


def segment_matrix(arm, head_world: Vector, tail_world: Vector) -> Matrix:
    inv = arm.matrix_world.inverted()
    head = inv @ head_world
    tail = inv @ tail_world
    direction = tail - head
    if direction.length < 1e-8:
        raise RuntimeError("joint-FK segment has zero length")
    rotation = direction.normalized().to_track_quat("Y", "Z")
    return Matrix.Translation(head) @ rotation.to_matrix().to_4x4()


def set_segment(arm, bone_name: str, head_world: Vector, tail_world: Vector, *, frame: int | None = None,
                length_tolerance: float = 0.002, result_tolerance: float = 0.006) -> None:
    bone = arm.pose.bones[bone_name]
    authored_length = (tail_world - head_world).length
    rig_length = float(bone.bone.length)
    if abs(authored_length - rig_length) > length_tolerance:
        raise RuntimeError(f"{bone_name} authored length {authored_length:.6f} != rig length {rig_length:.6f}")
    bone.rotation_mode = "QUATERNION"
    bone.matrix = segment_matrix(arm, head_world, tail_world)
    bpy.context.view_layer.update()
    actual_head = bone_head_world(arm, bone_name)
    actual_tail = bone_tail_world(arm, bone_name)
    error = max((actual_head - head_world).length, (actual_tail - tail_world).length)
    if error > result_tolerance:
        raise RuntimeError(f"{bone_name} deterministic solve error {error:.6f}")
    if frame is not None:
        bone.keyframe_insert(data_path="rotation_quaternion", frame=frame)


def joint_errors(arm, joint_pose: dict) -> dict[str, float]:
    expected = {
        "leftElbow": Vector(joint_pose["leftElbow"]), "leftWrist": Vector(joint_pose["leftWrist"]),
        "rightElbow": Vector(joint_pose["rightElbow"]), "rightWrist": Vector(joint_pose["rightWrist"]),
    }
    actual = {
        "leftElbow": bone_tail_world(arm, "LeftUpperArm"), "leftWrist": bone_tail_world(arm, "LeftForeArm"),
        "rightElbow": bone_tail_world(arm, "RightUpperArm"), "rightWrist": bone_tail_world(arm, "RightForeArm"),
    }
    return {name: round((actual[name] - expected[name]).length, 6) for name in expected}
