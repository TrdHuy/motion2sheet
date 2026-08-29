from __future__ import annotations

"""Deterministic arm pose utilities for key-pose architecture review."""

import bpy
from mathutils import Matrix, Vector


ARM_IK_BONES = ("LeftForeArm", "RightForeArm")
ARM_FK_BONES = (
    "LeftUpperArm", "LeftForeArm", "LeftHand",
    "RightUpperArm", "RightForeArm", "RightHand",
)


def set_arm_ik(arm, influence: float) -> None:
    for name in ARM_IK_BONES:
        constraint = arm.pose.bones[name].constraints.get("ReferenceIK_" + name)
        if constraint is None:
            raise RuntimeError(f"missing arm IK constraint for {name}")
        constraint.influence = float(influence)


def bone_head_world(arm, name: str) -> Vector:
    return arm.matrix_world @ arm.pose.bones[name].head


def bone_tail_world(arm, name: str) -> Vector:
    return arm.matrix_world @ arm.pose.bones[name].tail


def segment_matrix(arm, head_world: Vector, tail_world: Vector) -> Matrix:
    inv = arm.matrix_world.inverted()
    head = inv @ Vector(head_world)
    tail = inv @ Vector(tail_world)
    direction = tail - head
    if direction.length < 1e-8:
        raise RuntimeError("joint-FK segment has zero length")
    rotation = direction.normalized().to_track_quat("Y", "Z")
    return Matrix.Translation(head) @ rotation.to_matrix().to_4x4()


def set_bone_segment(
    arm,
    bone_name: str,
    head_world,
    tail_world,
    *,
    length_tolerance: float = 0.003,
    result_tolerance: float = 0.008,
) -> None:
    head_world = Vector(head_world)
    tail_world = Vector(tail_world)
    bone = arm.pose.bones[bone_name]
    expected = float(bone.bone.length)
    authored = (tail_world - head_world).length
    if abs(authored - expected) > length_tolerance:
        raise RuntimeError(
            f"{bone_name}: authored length {authored:.6f} != rig {expected:.6f}"
        )
    bone.rotation_mode = "QUATERNION"
    bone.matrix = segment_matrix(arm, head_world, tail_world)
    bpy.context.view_layer.update()
    head_error = (bone_head_world(arm, bone_name) - head_world).length
    tail_error = (bone_tail_world(arm, bone_name) - tail_world).length
    if max(head_error, tail_error) > result_tolerance:
        raise RuntimeError(
            f"{bone_name}: joint solve drifted head={head_error:.6f} tail={tail_error:.6f}"
        )


def apply_arm_pose(arm, sword, pose: dict) -> dict:
    """Apply exact shoulder->elbow->wrist chains and bind sword to both wrists."""
    set_arm_ik(arm, 0.0)
    bpy.context.view_layer.update()

    left_shoulder = bone_head_world(arm, "LeftUpperArm")
    right_shoulder = bone_head_world(arm, "RightUpperArm")
    left_elbow = Vector(pose["leftElbow"])
    left_wrist = Vector(pose["leftWrist"])
    right_elbow = Vector(pose["rightElbow"])
    right_wrist = Vector(pose["rightWrist"])

    set_bone_segment(arm, "LeftUpperArm", left_shoulder, left_elbow)
    set_bone_segment(arm, "LeftForeArm", left_elbow, left_wrist)
    set_bone_segment(arm, "RightUpperArm", right_shoulder, right_elbow)
    set_bone_segment(arm, "RightForeArm", right_elbow, right_wrist)

    grip_axis = right_wrist - left_wrist
    if grip_axis.length < 0.08:
        raise RuntimeError("two-hand grip sockets are too close")
    grip_axis.normalize()
    for hand_name, wrist in (("LeftHand", left_wrist), ("RightHand", right_wrist)):
        length = float(arm.pose.bones[hand_name].bone.length)
        set_bone_segment(arm, hand_name, wrist, wrist + grip_axis * length)

    sword.location = left_wrist
    sword.rotation_mode = "QUATERNION"
    sword.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(grip_axis)
    bpy.context.view_layer.update()

    actual = {
        "leftShoulder": bone_head_world(arm, "LeftUpperArm"),
        "leftElbow": bone_tail_world(arm, "LeftUpperArm"),
        "leftWrist": bone_tail_world(arm, "LeftForeArm"),
        "rightShoulder": bone_head_world(arm, "RightUpperArm"),
        "rightElbow": bone_tail_world(arm, "RightUpperArm"),
        "rightWrist": bone_tail_world(arm, "RightForeArm"),
    }
    errors = {}
    for name in ("leftElbow", "leftWrist", "rightElbow", "rightWrist"):
        errors[name] = (actual[name] - Vector(pose[name])).length
    return {
        "actual": actual,
        "errors": errors,
        "maxError": max(errors.values()),
        "gripDistance": (right_wrist - left_wrist).length,
    }
