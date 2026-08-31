"""Generic profile-driven humanoid Blender author.

Animation clips are data. This module consumes a rig profile, character/equipment
profile, pose reference and joint contract embedded in the resolved source spec.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import bpy
from mathutils import Vector

from motion2sheet.anim2sheet.common import equipment as equipment_runtime
from motion2sheet.anim2sheet.common.rig import humanoid as rig
from motion2sheet.anim2sheet.common.rig.arm_fk import arm_segments, disable_arm_ik, joint_errors, set_segment
from motion2sheet.anim2sheet.common.rig.leg_ik import configure_mirrored_poles


def argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def _profile(source: dict, key: str) -> dict:
    value = source.get(key)
    if not isinstance(value, dict):
        raise RuntimeError(f"source spec missing embedded {key}")
    return value


def _body_channels(rig_profile: dict) -> tuple[list[dict], list[dict], dict]:
    torso = rig_profile["solvers"]["torso"]
    return list(torso["bodyChannels"]), list(torso["clavicleChannels"]), torso


def _apply_body(arm, body: dict, rig_profile: dict, *, frame: int) -> None:
    channels, clavicles, torso = _body_channels(rig_profile)
    for row in channels:
        yaw_field, lean_field = str(row["yawField"]), str(row["leanField"])
        if yaw_field not in body or lean_field not in body:
            continue
        bone = arm.pose.bones[str(row["bone"])]
        rig.set_trunk_rotation(bone, body[yaw_field], body[lean_field], torso)
        bone.keyframe_insert(data_path="rotation_euler", frame=frame)
    for row in clavicles:
        field = str(row["field"])
        if field not in body:
            continue
        bone = arm.pose.bones[str(row["bone"])]
        axis = str(row.get("axis", "Z"))
        values = {"X": bone.rotation_euler.x, "Y": bone.rotation_euler.y, "Z": bone.rotation_euler.z}
        values[axis] = math.radians(float(body[field])) * float(row.get("sign", 1.0))
        bone.rotation_euler = (values["X"], values["Y"], values["Z"])
        bone.keyframe_insert(data_path="rotation_euler", frame=frame)


def apply_reference_pose(motion_root, arm, targets, equipment_item, equipment_profile: dict,
                         row: dict, rig_profile: dict) -> None:
    frame = int(row["frame"])
    bpy.context.scene.frame_set(frame)
    root_x, root_z = row["root"]
    motion_root.location = (float(root_x), 0.0, float(root_z))
    motion_root.keyframe_insert(data_path="location", frame=frame)
    _apply_body(arm, row["body"], rig_profile, frame=frame)
    row_targets = row["targets"]
    for target_row in rig_profile["targets"]:
        name = str(target_row["semantic"])
        targets[name].location = Vector(row_targets[name])
        targets[name].keyframe_insert(data_path="location", frame=frame)
    equipment_runtime.apply_reference_guides(equipment_item, equipment_profile, row_targets, frame=frame)


def apply_leg_override(targets: dict, joint_pose: dict, frame: int, rig_profile: dict) -> dict | None:
    override = joint_pose.get("legOverride")
    if override is None:
        return None
    if not isinstance(override, dict) or not override:
        raise RuntimeError(f"F{frame} legOverride must be a non-empty object")
    allowed = set(rig_profile["solvers"]["legs"].get("overrideTargets", []))
    unknown = set(override) - allowed
    if unknown:
        raise RuntimeError(f"F{frame} legOverride fields invalid: unknown={sorted(unknown)}")
    normalized = {}
    for name, values in override.items():
        if name not in targets:
            raise RuntimeError(f"F{frame} legOverride target does not exist: {name}")
        if not isinstance(values, list) or len(values) != 3:
            raise RuntimeError(f"F{frame} legOverride {name} must be a 3-number array")
        vector = [float(value) for value in values]
        targets[name].location = Vector(vector)
        targets[name].keyframe_insert(data_path="location", frame=frame)
        normalized[name] = vector
    bpy.context.view_layer.update()
    return normalized


def apply_body_override(arm, joint_pose: dict, frame: int, rig_profile: dict) -> dict | None:
    override = joint_pose.get("bodyOverride")
    if override is None:
        return None
    if not isinstance(override, dict):
        raise RuntimeError(f"F{frame} bodyOverride must be an object")
    required = set(rig_profile["solvers"]["torso"].get("overrideFields", []))
    unknown = set(override) - required
    missing = required - set(override)
    if unknown or missing:
        raise RuntimeError(f"F{frame} bodyOverride fields invalid: missing={sorted(missing)} unknown={sorted(unknown)}")
    _apply_body(arm, override, rig_profile, frame=frame)
    bpy.context.view_layer.update()
    return dict(override)


def apply_two_hand_arm_pose(arm, equipment_item, equipment_profile: dict, joint_pose: dict,
                            frame: int, rig_profile: dict) -> None:
    disable_arm_ik(arm, rig_profile)
    bpy.context.view_layer.update()
    segments = arm_segments(rig_profile)
    side_cfg = rig_profile["solvers"]["arms"]["sides"]
    joints = {}
    for side in ("left", "right"):
        elbow_key = str(side_cfg[side]["elbowPoseField"])
        wrist_key = str(side_cfg[side]["wristPoseField"])
        joints[elbow_key] = Vector(joint_pose[elbow_key])
        joints[wrist_key] = Vector(joint_pose[wrist_key])
        upper, fore, _hand = segments[side]
        shoulder = rig.bone_head_world(arm, upper)
        set_segment(arm, upper, shoulder, joints[elbow_key], frame=frame)
        set_segment(arm, fore, joints[elbow_key], joints[wrist_key], frame=frame)
    _primary, _secondary, grip_axis = equipment_runtime.bind_two_hand(
        equipment_item, equipment_profile["binding"], joint_pose, frame=frame
    )
    for side in ("left", "right"):
        hand = segments[side][2]
        wrist_key = str(side_cfg[side]["wristPoseField"])
        wrist = joints[wrist_key]
        length = float(arm.pose.bones[hand].bone.length)
        set_segment(arm, hand, wrist, wrist + grip_axis * length, frame=frame)
    bpy.context.view_layer.update()


def bend_angle(a: Vector, b: Vector, c: Vector) -> float:
    u, v = (a - b).normalized(), (c - b).normalized()
    dot = max(-1.0, min(1.0, float(u.dot(v))))
    return round(math.degrees(math.acos(dot)), 6)


def _joint_bones(rig_profile: dict) -> dict[str, tuple[str, str]]:
    arms = rig_profile["solvers"]["arms"]["sides"]
    legs = rig_profile["solvers"]["legs"]["sides"]
    return {
        "leftShoulder": (str(arms["left"]["upperBone"]), "head"),
        "leftElbow": (str(arms["left"]["upperBone"]), "tail"),
        "leftWrist": (str(arms["left"]["foreBone"]), "tail"),
        "rightShoulder": (str(arms["right"]["upperBone"]), "head"),
        "rightElbow": (str(arms["right"]["upperBone"]), "tail"),
        "rightWrist": (str(arms["right"]["foreBone"]), "tail"),
        "leftHip": (str(legs["left"]["thighBone"]), "head"),
        "leftKnee": (str(legs["left"]["thighBone"]), "tail"),
        "leftAnkle": (str(legs["left"]["shinBone"]), "tail"),
        "rightHip": (str(legs["right"]["thighBone"]), "head"),
        "rightKnee": (str(legs["right"]["thighBone"]), "tail"),
        "rightAnkle": (str(legs["right"]["shinBone"]), "tail"),
    }


def _bone_point(arm, bone_name: str, endpoint: str) -> Vector:
    return rig.bone_head_world(arm, bone_name) if endpoint == "head" else rig.bone_tail_world(arm, bone_name)


def body_state(arm, frame: int, joint_pose: dict, base_body: dict, rig_profile: dict) -> dict:
    effective = dict(base_body)
    if joint_pose.get("bodyOverride"):
        effective.update(joint_pose["bodyOverride"])
    arms = rig_profile["solvers"]["arms"]["sides"]
    return {
        "frame": frame,
        "bodyOverride": joint_pose.get("bodyOverride"),
        "legOverride": joint_pose.get("legOverride"),
        "effectiveBody": effective,
        "resultingShoulders": {
            "leftShoulder": rig.vector(rig.bone_head_world(arm, str(arms["left"]["upperBone"]))),
            "rightShoulder": rig.vector(rig.bone_head_world(arm, str(arms["right"]["upperBone"]))),
        },
    }


def sample_frame(motion_root, arm, equipment_item, equipment_profile: dict, frame: int,
                 joint_pose: dict, rig_profile: dict) -> dict:
    bpy.context.scene.frame_set(frame)
    bpy.context.view_layer.update()
    joints = {name: _bone_point(arm, bone, endpoint) for name, (bone, endpoint) in _joint_bones(rig_profile).items()}
    binding = equipment_profile["binding"]
    local_axis = Vector(binding.get("localAxis", [0, 0, 1])).normalized()
    tip_distance = float(binding.get("tipDistance", 1.20))
    weapon_grip = equipment_item.matrix_world @ Vector((0, 0, 0))
    weapon_tip = equipment_item.matrix_world @ (local_axis * tip_distance)
    primary_key = str(binding["primaryJoint"])
    secondary_key = str(binding["secondaryJoint"])
    expected_primary, expected_secondary = Vector(joint_pose[primary_key]), Vector(joint_pose[secondary_key])
    weapon_axis = (weapon_tip - weapon_grip).normalized()
    second_delta = expected_secondary - weapon_grip
    errors = joint_errors(arm, joint_pose, rig_profile)
    return {
        "frame": frame,
        "armPoseMode": str(rig_profile["solvers"]["arms"]["mode"]),
        "bodyOverride": joint_pose.get("bodyOverride"),
        "legOverride": joint_pose.get("legOverride"),
        "root": [round(motion_root.location.x, 6), round(motion_root.location.z, 6)],
        "joints": {name: rig.vector(point) for name, point in joints.items()},
        "armJointContractError": errors,
        "maxArmJointContractError": max(errors.values()),
        "leftElbowAngleDeg": bend_angle(joints["leftShoulder"], joints["leftElbow"], joints["leftWrist"]),
        "rightElbowAngleDeg": bend_angle(joints["rightShoulder"], joints["rightElbow"], joints["rightWrist"]),
        "leftArmExtension": round((joints["leftWrist"] - joints["leftShoulder"]).length, 6),
        "rightArmExtension": round((joints["rightWrist"] - joints["rightShoulder"]).length, 6),
        "leftKneeAngleDeg": bend_angle(joints["leftHip"], joints["leftKnee"], joints["leftAnkle"]),
        "rightKneeAngleDeg": bend_angle(joints["rightHip"], joints["rightKnee"], joints["rightAnkle"]),
        "stanceWidth": round(abs(joints["leftAnkle"].x - joints["rightAnkle"].x), 6),
        "swordGrip": rig.vector(weapon_grip),
        "swordTip": rig.vector(weapon_tip),
        "projectedSwordLengthXZ": round(math.hypot(weapon_tip.x - weapon_grip.x, weapon_tip.z - weapon_grip.z), 6),
        "weaponGripContract": {
            "primaryLeftWristError": round((weapon_grip - expected_primary).length, 6),
            "rightWristAxisError": round(second_delta.cross(weapon_axis).length, 6),
            "rightWristAlongGrip": round(float(second_delta.dot(weapon_axis)), 6),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--output", required=True)
    args, _ = parser.parse_known_args(argv())
    source = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    rig_profile = _profile(source, "rigProfileData")
    character_profile = _profile(source, "characterProfileData")
    reference = _profile(source, "poseReferenceData")
    contract = _profile(source, "jointContractData")
    execution_frames = [int(v) for v in source.get("executionFrames", contract["reviewFrames"])]
    invalid = [frame for frame in execution_frames if frame not in contract["reviewFrames"]]
    if not execution_frames or invalid:
        raise RuntimeError(f"invalid executionFrames: {execution_frames}; outside={invalid}")
    ref_by_frame = {int(row["frame"]): row for row in reference["keyPoses"]}
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    motion_root, arm = rig.build_root_and_rig(rig_profile)
    arm["anim2sheetRigProfileJson"] = json.dumps(rig_profile, separators=(",", ":"))
    rig.build_character(arm, character_profile)
    rig.add_review_connectors(arm, character_profile)
    targets = rig.build_pose_targets(arm, rig_profile)
    configure_mirrored_poles(arm, rig_profile)
    equipment = equipment_runtime.build_equipment(character_profile)
    equipment_profile, equipment_item = equipment_runtime.primary_equipment(character_profile, equipment)
    rig.setup_scene(source["canvas"])
    scene = bpy.context.scene
    rig.configure_review_render(scene)
    scene.frame_start, scene.frame_end = min(execution_frames), max(execution_frames)
    disable_arm_ik(arm, rig_profile)
    body_debug = []
    for frame in execution_frames:
        print(f"ANIM_BODY_START F{frame}", flush=True)
        base = ref_by_frame[frame]
        apply_reference_pose(motion_root, arm, targets, equipment_item, equipment_profile, base, rig_profile)
        joint_pose = contract["poses"][str(frame)]
        apply_leg_override(targets, joint_pose, frame, rig_profile)
        if "rootOverride" in joint_pose:
            root_x, root_z = joint_pose["rootOverride"]
            motion_root.location = (float(root_x), 0.0, float(root_z))
            motion_root.keyframe_insert(data_path="location", frame=frame)
        apply_body_override(arm, joint_pose, frame, rig_profile)
        bpy.context.view_layer.update()
        row = body_state(arm, frame, joint_pose, base["body"], rig_profile)
        body_debug.append(row)
        print(f"ANIM_BODY_OK F{frame} shoulders={row['resultingShoulders']}", flush=True)
    (output / "body_authoring_debug.json").write_text(json.dumps({"frames": body_debug}, indent=2) + "\n", encoding="utf-8")
    for frame in execution_frames:
        print(f"ANIM_ARM_SOLVE_START F{frame}", flush=True)
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        apply_two_hand_arm_pose(arm, equipment_item, equipment_profile, contract["poses"][str(frame)], frame, rig_profile)
        print(f"ANIM_ARM_SOLVE_OK F{frame}", flush=True)
    interpolation = str(source.get("interpolation", "LINEAR"))
    for owner in [motion_root, arm, equipment_item, *targets.values()]:
        rig.configure_interpolation(owner, execution_frames, interpolation)
    debug = {
        "action": source["action"],
        "mode": "review",
        "reviewFrames": execution_frames,
        "rig": arm.name,
        "rigProfile": source.get("rigProfileSource"),
        "characterProfile": source.get("characterProfileSource"),
        "authoringCapability": source["authoringCapability"],
        "armControl": rig_profile["solvers"]["arms"]["mode"],
        "legControl": rig_profile["solvers"]["legs"]["mode"],
        "torsoControl": rig_profile["solvers"]["torso"]["mode"],
        "weaponBinding": equipment_profile["binding"],
        "bodyAuthoring": body_debug,
        "samples": [
            sample_frame(motion_root, arm, equipment_item, equipment_profile, frame, contract["poses"][str(frame)], rig_profile)
            for frame in execution_frames
        ],
    }
    (output / "motion_debug.json").write_text(json.dumps(debug, indent=2) + "\n", encoding="utf-8")
    (output / "arm_joint_contract.json").write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    scene.frame_set(execution_frames[0])
    bpy.ops.wm.save_as_mainfile(filepath=str((output / "source.blend").resolve()))
    print(f"anim2sheet generic humanoid author/save OK: action={source['action']} frames={execution_frames}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
