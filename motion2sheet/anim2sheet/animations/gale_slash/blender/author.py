"""Gale Slash Blender authoring implementation.

Pose values remain data-driven. This module owns only Gale Slash-specific pose
application, overrides and two-hand weapon binding; reusable rig math lives in common/.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import bpy
from mathutils import Vector

from motion2sheet.anim2sheet.common.rig import humanoid as rig
from motion2sheet.anim2sheet.common.rig.arm_fk import ARM_SEGMENTS, disable_arm_ik, joint_errors, set_segment
from motion2sheet.anim2sheet.common.rig.leg_ik import configure_mirrored_poles
from motion2sheet.anim2sheet.animations.gale_slash.contract import load_joint_contract

BODY_FIELDS = {
    "Pelvis": ("pelvisYawDeg", "pelvisLeanDeg"),
    "Spine": ("spineYawDeg", "spineLeanDeg"),
    "Chest": ("chestYawDeg", "chestLeanDeg"),
    "Head": ("headYawDeg", "headLeanDeg"),
}
BODY_OVERRIDE_FIELDS = {
    "pelvisYawDeg", "pelvisLeanDeg", "spineYawDeg", "spineLeanDeg",
    "chestYawDeg", "chestLeanDeg", "leftClavicleSwingDeg", "rightClavicleSwingDeg",
}
LEG_OVERRIDE_FIELDS = {"leftAnkle", "rightAnkle", "leftKneeGuide", "rightKneeGuide"}


def argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def build_sword():
    steel = rig.material("Steel", (0.55, 0.62, 0.70), 0.75)
    grip_mat = rig.material("Grip", (0.12, 0.055, 0.025), 0.10)
    ctrl = rig.empty("SwordController")
    ctrl.rotation_mode = "QUATERNION"
    rig.controller_cylinder(ctrl, "SwordGrip", -0.08, 0.24, 0.045, grip_mat)
    rig.controller_cylinder(ctrl, "SwordBlade", 0.23, 1.20, 0.035, steel)
    return ctrl


def apply_reference_pose(motion_root, arm, targets, sword, row) -> None:
    frame = int(row["frame"])
    bpy.context.scene.frame_set(frame)
    root_x, root_z = row["root"]
    motion_root.location = (float(root_x), 0.0, float(root_z))
    motion_root.keyframe_insert(data_path="location", frame=frame)
    body = row["body"]
    for bone_name, (yaw_key, lean_key) in BODY_FIELDS.items():
        rig.set_trunk_rotation(arm.pose.bones[bone_name], body[yaw_key], body[lean_key])
        arm.pose.bones[bone_name].keyframe_insert(data_path="rotation_euler", frame=frame)
    arm.pose.bones["LeftClavicle"].rotation_euler.z = math.radians(float(body["leftClavicleSwingDeg"]))
    arm.pose.bones["RightClavicle"].rotation_euler.z = math.radians(-float(body["rightClavicleSwingDeg"]))
    arm.pose.bones["LeftClavicle"].keyframe_insert(data_path="rotation_euler", frame=frame)
    arm.pose.bones["RightClavicle"].keyframe_insert(data_path="rotation_euler", frame=frame)
    row_targets = row["targets"]
    for name in rig.TARGET_NAMES:
        targets[name].location = Vector(row_targets[name])
        targets[name].keyframe_insert(data_path="location", frame=frame)
    grip = Vector(row_targets["swordGrip"])
    tip = Vector(row_targets["swordTipGuide"])
    direction = tip - grip
    if direction.length < 1e-6:
        raise RuntimeError(f"frame {frame}: sword grip/tip guide are coincident")
    sword.location = grip
    sword.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(direction.normalized())
    sword.keyframe_insert(data_path="location", frame=frame)
    sword.keyframe_insert(data_path="rotation_quaternion", frame=frame)


def apply_leg_override(targets: dict, joint_pose: dict, frame: int) -> dict | None:
    override = joint_pose.get("legOverride")
    if override is None:
        return None
    if not isinstance(override, dict) or not override:
        raise RuntimeError(f"F{frame} legOverride must be a non-empty object")
    unknown = set(override) - LEG_OVERRIDE_FIELDS
    if unknown:
        raise RuntimeError(f"F{frame} legOverride fields invalid: unknown={sorted(unknown)}")
    normalized = {}
    for name, values in override.items():
        if not isinstance(values, list) or len(values) != 3:
            raise RuntimeError(f"F{frame} legOverride {name} must be a 3-number array")
        vector = [float(value) for value in values]
        targets[name].location = Vector(vector)
        targets[name].keyframe_insert(data_path="location", frame=frame)
        normalized[name] = vector
    bpy.context.view_layer.update()
    return normalized


def apply_body_override(arm, joint_pose: dict, frame: int) -> dict | None:
    override = joint_pose.get("bodyOverride")
    if override is None:
        return None
    if not isinstance(override, dict):
        raise RuntimeError(f"F{frame} bodyOverride must be an object")
    unknown = set(override) - BODY_OVERRIDE_FIELDS
    missing = BODY_OVERRIDE_FIELDS - set(override)
    if unknown or missing:
        raise RuntimeError(f"F{frame} bodyOverride fields invalid: missing={sorted(missing)} unknown={sorted(unknown)}")
    for bone_name, yaw_key, lean_key in (("Pelvis", "pelvisYawDeg", "pelvisLeanDeg"),
                                         ("Spine", "spineYawDeg", "spineLeanDeg"),
                                         ("Chest", "chestYawDeg", "chestLeanDeg")):
        rig.set_trunk_rotation(arm.pose.bones[bone_name], override[yaw_key], override[lean_key])
        arm.pose.bones[bone_name].keyframe_insert(data_path="rotation_euler", frame=frame)
    arm.pose.bones["LeftClavicle"].rotation_euler.z = math.radians(float(override["leftClavicleSwingDeg"]))
    arm.pose.bones["RightClavicle"].rotation_euler.z = math.radians(-float(override["rightClavicleSwingDeg"]))
    arm.pose.bones["LeftClavicle"].keyframe_insert(data_path="rotation_euler", frame=frame)
    arm.pose.bones["RightClavicle"].keyframe_insert(data_path="rotation_euler", frame=frame)
    bpy.context.view_layer.update()
    return dict(override)


def apply_two_hand_arm_pose(arm, sword, joint_pose: dict, frame: int) -> None:
    disable_arm_ik(arm)
    bpy.context.view_layer.update()
    joints = {name: Vector(joint_pose[name]) for name in ("leftElbow", "leftWrist", "rightElbow", "rightWrist")}
    for side in ("left", "right"):
        upper, fore, _hand = ARM_SEGMENTS[side]
        shoulder = rig.bone_head_world(arm, upper)
        elbow, wrist = joints[f"{side}Elbow"], joints[f"{side}Wrist"]
        set_segment(arm, upper, shoulder, elbow, frame=frame)
        set_segment(arm, fore, elbow, wrist, frame=frame)
    pommel, blade_hand = joints["leftWrist"], joints["rightWrist"]
    grip_axis = blade_hand - pommel
    if grip_axis.length < 0.08:
        raise RuntimeError("two-hand grip points are too close")
    grip_axis.normalize()
    sword.location = pommel
    sword.rotation_mode = "QUATERNION"
    sword.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(grip_axis)
    sword.keyframe_insert(data_path="location", frame=frame)
    sword.keyframe_insert(data_path="rotation_quaternion", frame=frame)
    for side in ("left", "right"):
        hand = ARM_SEGMENTS[side][2]
        wrist = joints[f"{side}Wrist"]
        length = float(arm.pose.bones[hand].bone.length)
        set_segment(arm, hand, wrist, wrist + grip_axis * length, frame=frame)
    bpy.context.view_layer.update()


def bend_angle(a: Vector, b: Vector, c: Vector) -> float:
    u, v = (a - b).normalized(), (c - b).normalized()
    dot = max(-1.0, min(1.0, float(u.dot(v))))
    return round(math.degrees(math.acos(dot)), 6)


def body_state(arm, frame: int, joint_pose: dict, base_body: dict) -> dict:
    effective = dict(base_body)
    if joint_pose.get("bodyOverride"):
        effective.update(joint_pose["bodyOverride"])
    return {"frame": frame, "bodyOverride": joint_pose.get("bodyOverride"), "legOverride": joint_pose.get("legOverride"),
            "effectiveBody": effective,
            "resultingShoulders": {"leftShoulder": rig.vector(rig.bone_head_world(arm, "LeftUpperArm")),
                                    "rightShoulder": rig.vector(rig.bone_head_world(arm, "RightUpperArm"))}}


def sample_frame(motion_root, arm, sword, frame: int, joint_pose: dict) -> dict:
    bpy.context.scene.frame_set(frame)
    bpy.context.view_layer.update()
    joints = {
        "leftShoulder": rig.bone_head_world(arm, "LeftUpperArm"), "leftElbow": rig.bone_tail_world(arm, "LeftUpperArm"),
        "leftWrist": rig.bone_tail_world(arm, "LeftForeArm"), "rightShoulder": rig.bone_head_world(arm, "RightUpperArm"),
        "rightElbow": rig.bone_tail_world(arm, "RightUpperArm"), "rightWrist": rig.bone_tail_world(arm, "RightForeArm"),
        "leftHip": rig.bone_head_world(arm, "LeftThigh"), "leftKnee": rig.bone_tail_world(arm, "LeftThigh"),
        "leftAnkle": rig.bone_tail_world(arm, "LeftShin"), "rightHip": rig.bone_head_world(arm, "RightThigh"),
        "rightKnee": rig.bone_tail_world(arm, "RightThigh"), "rightAnkle": rig.bone_tail_world(arm, "RightShin"),
    }
    sword_grip = sword.matrix_world @ Vector((0, 0, 0))
    sword_tip = sword.matrix_world @ Vector((0, 0, 1.20))
    expected_left, expected_right = Vector(joint_pose["leftWrist"]), Vector(joint_pose["rightWrist"])
    sword_axis = (sword_tip - sword_grip).normalized()
    second_delta = expected_right - sword_grip
    errors = joint_errors(arm, joint_pose)
    return {"frame": frame, "armPoseMode": "deterministic_joint_fk", "bodyOverride": joint_pose.get("bodyOverride"),
            "legOverride": joint_pose.get("legOverride"),
            "root": [round(motion_root.location.x, 6), round(motion_root.location.z, 6)],
            "joints": {name: rig.vector(point) for name, point in joints.items()}, "armJointContractError": errors,
            "maxArmJointContractError": max(errors.values()),
            "leftElbowAngleDeg": bend_angle(joints["leftShoulder"], joints["leftElbow"], joints["leftWrist"]),
            "rightElbowAngleDeg": bend_angle(joints["rightShoulder"], joints["rightElbow"], joints["rightWrist"]),
            "leftArmExtension": round((joints["leftWrist"] - joints["leftShoulder"]).length, 6),
            "rightArmExtension": round((joints["rightWrist"] - joints["rightShoulder"]).length, 6),
            "leftKneeAngleDeg": bend_angle(joints["leftHip"], joints["leftKnee"], joints["leftAnkle"]),
            "rightKneeAngleDeg": bend_angle(joints["rightHip"], joints["rightKnee"], joints["rightAnkle"]),
            "stanceWidth": round(abs(joints["leftAnkle"].x - joints["rightAnkle"].x), 6),
            "swordGrip": rig.vector(sword_grip), "swordTip": rig.vector(sword_tip),
            "projectedSwordLengthXZ": round(math.hypot(sword_tip.x - sword_grip.x, sword_tip.z - sword_grip.z), 6),
            "weaponGripContract": {"primaryLeftWristError": round((sword_grip - expected_left).length, 6),
                                   "rightWristAxisError": round(second_delta.cross(sword_axis).length, 6),
                                   "rightWristAlongGrip": round(float(second_delta.dot(sword_axis)), 6)}}


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--joint-contract", required=True)
    parser.add_argument("--output", required=True)
    args, _ = parser.parse_known_args(argv())
    source = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    reference = source.get("poseReferenceData")
    if not isinstance(reference, dict):
        raise RuntimeError("source spec missing embedded poseReferenceData")
    contract = load_joint_contract(args.joint_contract)
    execution_frames = [int(v) for v in source.get("executionFrames", contract["reviewFrames"])]
    invalid = [frame for frame in execution_frames if frame not in contract["reviewFrames"]]
    if not execution_frames or invalid:
        raise RuntimeError(f"invalid executionFrames: {execution_frames}; outside={invalid}")
    ref_by_frame = {int(row["frame"]): row for row in reference["keyPoses"]}
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    motion_root, arm = rig.build_root_and_rig()
    rig.build_character(arm)
    rig.add_review_connectors(arm)
    targets = rig.build_pose_targets(arm)
    configure_mirrored_poles(arm)
    sword = build_sword()
    rig.setup_scene(source["canvas"])
    scene = bpy.context.scene
    rig.configure_review_render(scene)
    scene.frame_start, scene.frame_end = min(execution_frames), max(execution_frames)
    disable_arm_ik(arm)
    body_debug = []
    for frame in execution_frames:
        print(f"ANIM_BODY_START F{frame}", flush=True)
        base = ref_by_frame[frame]
        apply_reference_pose(motion_root, arm, targets, sword, base)
        joint_pose = contract["poses"][str(frame)]
        apply_leg_override(targets, joint_pose, frame)
        if "rootOverride" in joint_pose:
            root_x, root_z = joint_pose["rootOverride"]
            motion_root.location = (float(root_x), 0.0, float(root_z))
            motion_root.keyframe_insert(data_path="location", frame=frame)
        apply_body_override(arm, joint_pose, frame)
        bpy.context.view_layer.update()
        row = body_state(arm, frame, joint_pose, base["body"])
        body_debug.append(row)
        print(f"ANIM_BODY_OK F{frame} shoulders={row['resultingShoulders']}", flush=True)
    (output / "body_authoring_debug.json").write_text(json.dumps({"frames": body_debug}, indent=2) + "\n", encoding="utf-8")
    for frame in execution_frames:
        print(f"ANIM_ARM_SOLVE_START F{frame}", flush=True)
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        apply_two_hand_arm_pose(arm, sword, contract["poses"][str(frame)], frame)
        print(f"ANIM_ARM_SOLVE_OK F{frame}", flush=True)
    for owner in [motion_root, arm, sword, *targets.values()]:
        rig.configure_interpolation(owner, set(execution_frames))
    debug = {"action": source["action"], "mode": "review", "reviewFrames": execution_frames, "rig": arm.name,
             "armControl": "deterministic_joint_fk", "legControl": "ik_with_explicit_knee_poles",
             "torsoControl": "fk_with_body_overrides", "weaponBinding": contract["weaponBinding"],
             "bodyAuthoring": body_debug,
             "samples": [sample_frame(motion_root, arm, sword, frame, contract["poses"][str(frame)]) for frame in execution_frames]}
    (output / "motion_debug.json").write_text(json.dumps(debug, indent=2) + "\n", encoding="utf-8")
    (output / "arm_joint_contract.json").write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    scene.frame_set(execution_frames[0])
    bpy.ops.wm.save_as_mainfile(filepath=str((output / "source.blend").resolve()))
    print(f"anim2sheet Gale Slash author/save OK: {execution_frames}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
