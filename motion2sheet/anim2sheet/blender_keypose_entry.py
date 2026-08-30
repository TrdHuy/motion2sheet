"""Fast Blender authoring stage for deterministic key-pose review.

Only F1/F6/F7/F8 are authored. This stage authors the pose exactly once and
saves authoritative source.blend. Camera-specific rendering happens later by
reopening that saved blend, so multi-camera review cannot re-author motion.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import bpy
from mathutils import Vector

from motion2sheet.anim2sheet import blender_entry as legacy
from motion2sheet.anim2sheet.blender_entry_joint_fk import (
    apply_arm_pose,
    joint_errors,
    load_joint_contract,
)

BODY_OVERRIDE_FIELDS = {
    "pelvisYawDeg", "pelvisLeanDeg", "spineYawDeg", "spineLeanDeg",
    "chestYawDeg", "chestLeanDeg", "leftClavicleSwingDeg", "rightClavicleSwingDeg",
}
LEG_OVERRIDE_FIELDS = {
    "leftAnkle", "rightAnkle", "leftKneeGuide", "rightKneeGuide",
}


def argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def bend_angle(a: Vector, b: Vector, c: Vector) -> float:
    u = (a - b).normalized()
    v = (c - b).normalized()
    dot = max(-1.0, min(1.0, float(u.dot(v))))
    return round(math.degrees(math.acos(dot)), 6)


def configure_fast_render(scene) -> None:
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.film_transparent = True
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = False
    scene.display.shading.show_cavity = True
    scene.display.shading.background_type = "WORLD"


def add_fast_review_connectors(arm) -> None:
    cloth = bpy.data.materials.get("Cloth")
    skin = bpy.data.materials.get("Skin")
    boots = bpy.data.materials.get("Boots")
    if cloth is None or skin is None or boots is None:
        raise RuntimeError("legacy proxy materials missing before fast-review connectors")
    bones = arm.data.bones
    for name, radius, mat in [
        ("Neck", 0.065, skin), ("LeftClavicle", 0.055, cloth),
        ("RightClavicle", 0.055, cloth), ("LeftHand", 0.055, skin),
        ("RightHand", 0.055, skin), ("LeftFoot", 0.075, boots),
        ("RightFoot", 0.075, boots),
    ]:
        bone = bones[name]
        legacy.weighted_cylinder(arm, "Review_" + name, name, bone.head_local, bone.tail_local, radius, mat)
    motion_root = arm.parent
    if motion_root is None:
        raise RuntimeError("review armature must be parented to MotionRoot")
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH":
            obj.parent = motion_root


def configure_leg_ik_conventions(arm) -> None:
    """Compensate Blender's mirrored right-leg pole reference deterministically."""
    left = arm.pose.bones["LeftShin"].constraints["ReferenceIK_LeftShin"]
    right = arm.pose.bones["RightShin"].constraints["ReferenceIK_RightShin"]
    left.pole_angle = 0.0
    right.pole_angle = math.pi


def apply_leg_override(targets: dict, joint_pose: dict, frame: int) -> dict | None:
    """Apply optional fast-review leg target edits without changing base reference."""
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
        try:
            vector = [float(value) for value in values]
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"F{frame} legOverride {name} must be numeric") from exc
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
        raise RuntimeError(
            f"F{frame} bodyOverride fields invalid: missing={sorted(missing)} unknown={sorted(unknown)}"
        )
    for bone_name, yaw_key, lean_key in (
        ("Pelvis", "pelvisYawDeg", "pelvisLeanDeg"),
        ("Spine", "spineYawDeg", "spineLeanDeg"),
        ("Chest", "chestYawDeg", "chestLeanDeg"),
    ):
        legacy.set_trunk_rotation(arm.pose.bones[bone_name], override[yaw_key], override[lean_key])
        arm.pose.bones[bone_name].keyframe_insert(data_path="rotation_euler", frame=frame)
    arm.pose.bones["LeftClavicle"].rotation_euler.z = math.radians(float(override["leftClavicleSwingDeg"]))
    arm.pose.bones["RightClavicle"].rotation_euler.z = math.radians(-float(override["rightClavicleSwingDeg"]))
    arm.pose.bones["LeftClavicle"].keyframe_insert(data_path="rotation_euler", frame=frame)
    arm.pose.bones["RightClavicle"].keyframe_insert(data_path="rotation_euler", frame=frame)
    bpy.context.view_layer.update()
    return dict(override)


def body_state(arm, frame: int, joint_pose: dict, base_body: dict) -> dict:
    effective = dict(base_body)
    if joint_pose.get("bodyOverride"):
        effective.update(joint_pose["bodyOverride"])
    return {
        "frame": frame,
        "bodyOverride": joint_pose.get("bodyOverride"),
        "legOverride": joint_pose.get("legOverride"),
        "effectiveBody": effective,
        "resultingShoulders": {
            "leftShoulder": legacy.vector(legacy.bone_head_world(arm, "LeftUpperArm")),
            "rightShoulder": legacy.vector(legacy.bone_head_world(arm, "RightUpperArm")),
        },
    }


def sample_frame(motion_root, arm, sword, frame: int, joint_pose: dict) -> dict:
    bpy.context.scene.frame_set(frame)
    bpy.context.view_layer.update()
    joints = {
        "leftShoulder": legacy.bone_head_world(arm, "LeftUpperArm"),
        "leftElbow": legacy.bone_tail_world(arm, "LeftUpperArm"),
        "leftWrist": legacy.bone_tail_world(arm, "LeftForeArm"),
        "rightShoulder": legacy.bone_head_world(arm, "RightUpperArm"),
        "rightElbow": legacy.bone_tail_world(arm, "RightUpperArm"),
        "rightWrist": legacy.bone_tail_world(arm, "RightForeArm"),
        "leftHip": legacy.bone_head_world(arm, "LeftThigh"),
        "leftKnee": legacy.bone_tail_world(arm, "LeftThigh"),
        "leftAnkle": legacy.bone_tail_world(arm, "LeftShin"),
        "rightHip": legacy.bone_head_world(arm, "RightThigh"),
        "rightKnee": legacy.bone_tail_world(arm, "RightThigh"),
        "rightAnkle": legacy.bone_tail_world(arm, "RightShin"),
    }
    sword_grip = sword.matrix_world @ Vector((0, 0, 0))
    sword_tip = sword.matrix_world @ Vector((0, 0, 1.20))
    expected_left = Vector(joint_pose["leftWrist"])
    expected_right = Vector(joint_pose["rightWrist"])
    sword_axis = (sword_tip - sword_grip).normalized()
    second_delta = expected_right - sword_grip
    errors = joint_errors(arm, joint_pose)
    return {
        "frame": frame,
        "armPoseMode": "deterministic_joint_fk",
        "bodyOverride": joint_pose.get("bodyOverride"),
        "legOverride": joint_pose.get("legOverride"),
        "root": [round(motion_root.location.x, 6), round(motion_root.location.z, 6)],
        "joints": {name: legacy.vector(point) for name, point in joints.items()},
        "armJointContractError": errors,
        "maxArmJointContractError": max(errors.values()),
        "leftElbowAngleDeg": bend_angle(joints["leftShoulder"], joints["leftElbow"], joints["leftWrist"]),
        "rightElbowAngleDeg": bend_angle(joints["rightShoulder"], joints["rightElbow"], joints["rightWrist"]),
        "leftArmExtension": round((joints["leftWrist"] - joints["leftShoulder"]).length, 6),
        "rightArmExtension": round((joints["rightWrist"] - joints["rightShoulder"]).length, 6),
        "leftKneeAngleDeg": bend_angle(joints["leftHip"], joints["leftKnee"], joints["leftAnkle"]),
        "rightKneeAngleDeg": bend_angle(joints["rightHip"], joints["rightKnee"], joints["rightAnkle"]),
        "stanceWidth": round(abs(joints["leftAnkle"].x - joints["rightAnkle"].x), 6),
        "swordGrip": legacy.vector(sword_grip),
        "swordTip": legacy.vector(sword_tip),
        "projectedSwordLengthXZ": round(math.hypot(sword_tip.x - sword_grip.x, sword_tip.z - sword_grip.z), 6),
        "weaponGripContract": {
            "primaryLeftWristError": round((sword_grip - expected_left).length, 6),
            "rightWristAxisError": round(second_delta.cross(sword_axis).length, 6),
            "rightWristAlongGrip": round(float(second_delta.dot(sword_axis)), 6),
        },
    }


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
    joint_contract = load_joint_contract(args.joint_contract)
    review_frames = [int(v) for v in joint_contract["reviewFrames"]]
    ref_by_frame = {int(row["frame"]): row for row in reference["keyPoses"]}
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    motion_root, arm = legacy.build_root_and_rig()
    legacy.build_character(arm)
    add_fast_review_connectors(arm)
    targets = legacy.build_pose_targets(arm)
    configure_leg_ik_conventions(arm)
    sword = legacy.build_sword()
    legacy.setup_scene(source["canvas"])
    scene = bpy.context.scene
    configure_fast_render(scene)
    scene.frame_start = min(review_frames)
    scene.frame_end = max(review_frames)
    for name in ("LeftForeArm", "RightForeArm"):
        arm.pose.bones[name].constraints[f"ReferenceIK_{name}"].influence = 0.0

    body_debug = []
    for frame in review_frames:
        print(f"KEYPOSE_BODY_START F{frame}", flush=True)
        base = ref_by_frame[frame]
        legacy.key_pose(motion_root, arm, targets, sword, base)
        joint_pose = joint_contract["poses"][str(frame)]
        apply_leg_override(targets, joint_pose, frame)
        if "rootOverride" in joint_pose:
            root_x, root_z = joint_pose["rootOverride"]
            motion_root.location = (float(root_x), 0.0, float(root_z))
            motion_root.keyframe_insert(data_path="location", frame=frame)
        apply_body_override(arm, joint_pose, frame)
        bpy.context.view_layer.update()
        row = body_state(arm, frame, joint_pose, base["body"])
        body_debug.append(row)
        print(f"KEYPOSE_BODY_OK F{frame} shoulders={row['resultingShoulders']}", flush=True)
    (output / "body_authoring_debug.json").write_text(json.dumps({"frames": body_debug}, indent=2) + "\n", encoding="utf-8")

    for frame in review_frames:
        print(f"KEYPOSE_ARM_SOLVE_START F{frame}", flush=True)
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        apply_arm_pose(arm, sword, joint_contract["poses"][str(frame)], frame=frame)
        print(f"KEYPOSE_ARM_SOLVE_OK F{frame}", flush=True)
    for owner in [motion_root, arm, sword, *targets.values()]:
        legacy.configure_interpolation(owner, set(review_frames))

    debug = {
        "action": source["action"], "mode": "fast-keypose-review", "reviewFrames": review_frames,
        "rig": arm.name, "armControl": "deterministic_joint_fk",
        "legControl": "ik_with_explicit_knee_poles", "torsoControl": "fk_with_fast_body_overrides",
        "weaponBinding": joint_contract["weaponBinding"], "bodyAuthoring": body_debug,
        "samples": [sample_frame(motion_root, arm, sword, frame, joint_contract["poses"][str(frame)]) for frame in review_frames],
    }
    (output / "motion_debug.json").write_text(json.dumps(debug, indent=2) + "\n", encoding="utf-8")
    (output / "arm_joint_contract.json").write_text(json.dumps(joint_contract, indent=2) + "\n", encoding="utf-8")
    scene.frame_set(review_frames[0])
    bpy.ops.wm.save_as_mainfile(filepath=str((output / "source.blend").resolve()))
    print(f"anim2sheet key-pose author/save OK: {review_frames}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
