"""Generic Profile Contract v2 humanoid Blender author.

A clip supplies one canonical Motion frame at a time. Rig mechanics define how
those semantic channels are interpreted; Character owns visuals/equipment.
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
from motion2sheet.anim2sheet.common.rig.arm_fk import arm_segments, joint_errors, set_segment
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
            raise RuntimeError(f"F{frame} missing torso motion channels: {yaw_field}, {lean_field}")
        bone = arm.pose.bones[str(row["bone"])]
        rig.set_trunk_rotation(bone, body[yaw_field], body[lean_field], torso)
        bone.keyframe_insert(data_path="rotation_euler", frame=frame)
    for row in clavicles:
        field = str(row["field"])
        if field not in body:
            raise RuntimeError(f"F{frame} missing clavicle motion channel: {field}")
        bone = arm.pose.bones[str(row["bone"])]
        axis = str(row.get("axis", "Z"))
        values = {"X": bone.rotation_euler.x, "Y": bone.rotation_euler.y, "Z": bone.rotation_euler.z}
        values[axis] = math.radians(float(body[field])) * float(row.get("sign", 1.0))
        bone.rotation_euler = (values["X"], values["Y"], values["Z"])
        bone.keyframe_insert(data_path="rotation_euler", frame=frame)


def apply_two_hand_arm_pose(arm, equipment_item, equipment_profile: dict, joints: dict,
                            frame: int, rig_profile: dict) -> None:
    bpy.context.view_layer.update()
    segments = arm_segments(rig_profile)
    side_cfg = rig_profile["solvers"]["arms"]["sides"]
    resolved = {}
    for side in ("left", "right"):
        elbow_key = str(side_cfg[side]["elbowJoint"])
        wrist_key = str(side_cfg[side]["wristJoint"])
        resolved[elbow_key] = Vector(joints[elbow_key])
        resolved[wrist_key] = Vector(joints[wrist_key])
        upper, fore, _hand = segments[side]
        shoulder = rig.bone_head_world(arm, upper)
        set_segment(arm, upper, shoulder, resolved[elbow_key], frame=frame)
        set_segment(arm, fore, resolved[elbow_key], resolved[wrist_key], frame=frame)
    _primary, _secondary, grip_axis = equipment_runtime.bind_two_hand(
        equipment_item, equipment_profile["binding"], joints, frame=frame
    )
    for side in ("left", "right"):
        hand = segments[side][2]
        wrist_key = str(side_cfg[side]["wristJoint"])
        wrist = resolved[wrist_key]
        length = float(arm.pose.bones[hand].bone.length)
        set_segment(arm, hand, wrist, wrist + grip_axis * length, frame=frame)
    bpy.context.view_layer.update()


def apply_motion_frame(motion_root, arm, targets: dict, equipment_item, equipment_profile: dict,
                       frame_state: dict, rig_profile: dict) -> None:
    frame = int(frame_state["frame"])
    bpy.context.scene.frame_set(frame)
    motion_root.location = Vector(frame_state["root"]["translation"])
    motion_root.keyframe_insert(data_path="location", frame=frame)
    _apply_body(arm, frame_state["body"], rig_profile, frame=frame)
    for semantic, values in frame_state["targets"].items():
        if semantic not in targets:
            raise RuntimeError(f"F{frame} motion target does not exist in rig: {semantic}")
        targets[semantic].location = Vector(values)
        targets[semantic].keyframe_insert(data_path="location", frame=frame)
    bpy.context.view_layer.update()
    apply_two_hand_arm_pose(arm, equipment_item, equipment_profile, frame_state["joints"], frame, rig_profile)


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


def body_state(arm, frame_state: dict, rig_profile: dict) -> dict:
    arms = rig_profile["solvers"]["arms"]["sides"]
    return {
        "frame": int(frame_state["frame"]),
        "motionBody": dict(frame_state["body"]),
        "resultingShoulders": {
            "leftShoulder": rig.vector(rig.bone_head_world(arm, str(arms["left"]["upperBone"]))),
            "rightShoulder": rig.vector(rig.bone_head_world(arm, str(arms["right"]["upperBone"]))),
        },
    }


def sample_frame(motion_root, arm, equipment_item, equipment_profile: dict,
                 frame_state: dict, rig_profile: dict) -> dict:
    frame = int(frame_state["frame"])
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
    expected_primary = Vector(frame_state["joints"][primary_key])
    expected_secondary = Vector(frame_state["joints"][secondary_key])
    weapon_axis = (weapon_tip - weapon_grip).normalized()
    second_delta = expected_secondary - weapon_grip
    errors = joint_errors(arm, frame_state["joints"], rig_profile)
    return {
        "frame": frame,
        "armPoseMode": str(rig_profile["solvers"]["arms"]["mode"]),
        "rootTranslation": rig.vector(motion_root.location),
        "joints": {name: rig.vector(point) for name, point in joints.items()},
        "armJointError": errors,
        "maxArmJointError": max(errors.values()),
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
    animation_profile = _profile(source, "animationProfileData")
    motion_profile = _profile(source, "motionProfileData")
    rig_profile = _profile(source, "rigProfileData")
    character_profile = _profile(source, "characterProfileData")
    motion_by_frame = {int(row["frame"]): row for row in motion_profile["frames"]}
    execution_frames = [int(v) for v in source.get("executionFrames", sorted(motion_by_frame))]
    invalid = [frame for frame in execution_frames if frame not in motion_by_frame]
    if not execution_frames or invalid:
        raise RuntimeError(f"invalid executionFrames: {execution_frames}; outside={invalid}")

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
    rig.setup_scene(animation_profile["render"]["canvas"])
    scene = bpy.context.scene
    rig.configure_review_render(scene)
    scene.frame_start, scene.frame_end = min(execution_frames), max(execution_frames)

    body_debug = []
    for frame in execution_frames:
        print(f"ANIM_MOTION_START F{frame}", flush=True)
        frame_state = motion_by_frame[frame]
        apply_motion_frame(motion_root, arm, targets, equipment_item, equipment_profile, frame_state, rig_profile)
        bpy.context.view_layer.update()
        row = body_state(arm, frame_state, rig_profile)
        body_debug.append(row)
        print(f"ANIM_MOTION_OK F{frame} shoulders={row['resultingShoulders']}", flush=True)
    (output / "body_authoring_debug.json").write_text(json.dumps({"frames": body_debug}, indent=2) + "\n", encoding="utf-8")

    interpolation = str(animation_profile.get("interpolation", "LINEAR"))
    for owner in [motion_root, arm, equipment_item, *targets.values()]:
        rig.configure_interpolation(owner, execution_frames, interpolation)
    debug = {
        "action": source["animation"],
        "mode": "review",
        "reviewFrames": execution_frames,
        "rig": arm.name,
        "rigProfile": source.get("rigProfileSource"),
        "motionProfile": source.get("motionProfileSource"),
        "characterProfile": source.get("characterProfileSource"),
        "authoringCapability": source["authoringCapability"],
        "armControl": rig_profile["solvers"]["arms"]["mode"],
        "legControl": rig_profile["solvers"]["legs"]["mode"],
        "torsoControl": rig_profile["solvers"]["torso"]["mode"],
        "weaponBinding": equipment_profile["binding"],
        "bodyAuthoring": body_debug,
        "samples": [sample_frame(motion_root, arm, equipment_item, equipment_profile, motion_by_frame[frame], rig_profile) for frame in execution_frames],
    }
    (output / "motion_debug.json").write_text(json.dumps(debug, indent=2) + "\n", encoding="utf-8")
    scene.frame_set(execution_frames[0])
    bpy.ops.wm.save_as_mainfile(filepath=str((output / "source.blend").resolve()))
    print(f"anim2sheet generic humanoid author/save OK: action={source['animation']} frames={execution_frames}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
