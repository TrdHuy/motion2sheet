"""Deterministic joint-driven FK arm solver for key-pose review.

Torso/clavicles remain authored FK. Legs keep the existing IK targets/poles.
Arms do not use wrist endpoint IK: exact elbow/wrist joints are authored and
converted to bone pose matrices deterministically. Sword orientation is derived
from the two authored wrist/grip points so hand/weapon topology cannot drift.
"""
from __future__ import annotations

import json
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

from motion2sheet.anim2sheet import blender_entry as legacy


ARM_IK_BONES = ("LeftForeArm", "RightForeArm")
ARM_SEGMENTS = {
    "left": ("LeftUpperArm", "LeftForeArm", "LeftHand"),
    "right": ("RightUpperArm", "RightForeArm", "RightHand"),
}


def load_joint_contract(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("armControl") != "deterministic_joint_fk":
        raise RuntimeError("joint contract must use deterministic_joint_fk")
    review_frames = [int(v) for v in data.get("reviewFrames", [])]
    if review_frames != [1, 6, 7, 8]:
        raise RuntimeError(f"expected reviewFrames [1, 6, 7, 8], got {review_frames}")
    poses = data.get("poses", {})
    for frame in review_frames:
        row = poses.get(str(frame))
        if not isinstance(row, dict):
            raise RuntimeError(f"joint contract missing frame {frame}")
        for name in ("leftElbow", "leftWrist", "rightElbow", "rightWrist"):
            value = row.get(name)
            if not isinstance(value, list) or len(value) != 3:
                raise RuntimeError(f"F{frame} {name} must be a 3D position")
    return data


def disable_arm_ik(arm) -> None:
    for bone_name in ARM_IK_BONES:
        constraint = arm.pose.bones[bone_name].constraints.get(
            f"ReferenceIK_{bone_name}"
        )
        if constraint is None:
            raise RuntimeError(f"missing legacy arm IK constraint on {bone_name}")
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


def set_segment(
    arm,
    bone_name: str,
    head_world: Vector,
    tail_world: Vector,
    *,
    frame: int | None = None,
    length_tolerance: float = 0.002,
    result_tolerance: float = 0.006,
) -> None:
    bone = arm.pose.bones[bone_name]
    authored_length = (tail_world - head_world).length
    rig_length = float(bone.bone.length)
    if abs(authored_length - rig_length) > length_tolerance:
        raise RuntimeError(
            f"{bone_name} authored length {authored_length:.6f} "
            f"!= rig length {rig_length:.6f}"
        )
    bone.rotation_mode = "QUATERNION"
    bone.matrix = segment_matrix(arm, head_world, tail_world)
    bpy.context.view_layer.update()
    actual_head = legacy.bone_head_world(arm, bone_name)
    actual_tail = legacy.bone_tail_world(arm, bone_name)
    error = max((actual_head - head_world).length, (actual_tail - tail_world).length)
    if error > result_tolerance:
        raise RuntimeError(f"{bone_name} deterministic solve error {error:.6f}")
    if frame is not None:
        bone.keyframe_insert(data_path="rotation_quaternion", frame=frame)


def apply_arm_pose(arm, sword, joint_pose: dict, *, frame: int | None = None) -> None:
    disable_arm_ik(arm)
    bpy.context.view_layer.update()

    joints = {
        "leftElbow": Vector(joint_pose["leftElbow"]),
        "leftWrist": Vector(joint_pose["leftWrist"]),
        "rightElbow": Vector(joint_pose["rightElbow"]),
        "rightWrist": Vector(joint_pose["rightWrist"]),
    }

    for side in ("left", "right"):
        upper_name, fore_name, _hand_name = ARM_SEGMENTS[side]
        shoulder = legacy.bone_head_world(arm, upper_name)
        elbow = joints[f"{side}Elbow"]
        wrist = joints[f"{side}Wrist"]
        set_segment(arm, upper_name, shoulder, elbow, frame=frame)
        set_segment(arm, fore_name, elbow, wrist, frame=frame)

    pommel = joints["leftWrist"]
    blade_hand = joints["rightWrist"]
    grip_axis = blade_hand - pommel
    if grip_axis.length < 0.08:
        raise RuntimeError("two-hand grip points are too close")
    grip_axis.normalize()
    sword.location = pommel
    sword.rotation_mode = "QUATERNION"
    sword.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(grip_axis)
    if frame is not None:
        sword.keyframe_insert(data_path="location", frame=frame)
        sword.keyframe_insert(data_path="rotation_quaternion", frame=frame)

    for side in ("left", "right"):
        hand_name = ARM_SEGMENTS[side][2]
        wrist = joints[f"{side}Wrist"]
        length = float(arm.pose.bones[hand_name].bone.length)
        set_segment(
            arm,
            hand_name,
            wrist,
            wrist + grip_axis * length,
            frame=frame,
        )

    bpy.context.view_layer.update()


def joint_errors(arm, joint_pose: dict) -> dict[str, float]:
    expected = {
        "leftElbow": Vector(joint_pose["leftElbow"]),
        "leftWrist": Vector(joint_pose["leftWrist"]),
        "rightElbow": Vector(joint_pose["rightElbow"]),
        "rightWrist": Vector(joint_pose["rightWrist"]),
    }
    actual = {
        "leftElbow": legacy.bone_tail_world(arm, "LeftUpperArm"),
        "leftWrist": legacy.bone_tail_world(arm, "LeftForeArm"),
        "rightElbow": legacy.bone_tail_world(arm, "RightUpperArm"),
        "rightWrist": legacy.bone_tail_world(arm, "RightForeArm"),
    }
    return {
        name: round((actual[name] - expected[name]).length, 6)
        for name in expected
    }
