"""Fast Blender runner for deterministic arm architecture review.

Only F1/F6/F7/F8 are rendered. The original 16-frame pose reference still
provides torso FK and leg IK values, while arm joints come from the dedicated
joint-FK key-pose contract. Fast review intentionally uses Workbench rendering:
this phase judges pose topology and silhouette, not final lighting quality.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

# Blender's bundled Python does not inherit the editable package installed into
# the GitHub runner's CPython. Add the checkout root explicitly before importing
# motion2sheet so this script behaves the same locally and in CI.
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
    """Fill only proxy gaps that are stable under deterministic review poses.

    The legacy proxy omits neck/hand/foot cylinders. Adding those connectors
    improves readability, but clavicle cylinders are intentionally excluded:
    the proxy's single-bone deformation can visually drift under large parent
    rotations even while the evaluated armature is correct. Fast review should
    never introduce geometry that contradicts the skeleton being inspected.
    """
    skin = bpy.data.materials.get("Skin")
    boots = bpy.data.materials.get("Boots")
    if skin is None or boots is None:
        raise RuntimeError("legacy proxy materials missing before fast-review connectors")

    bones = arm.data.bones
    segments = [
        ("Neck", 0.065, skin),
        ("LeftHand", 0.055, skin),
        ("RightHand", 0.055, skin),
        ("LeftFoot", 0.075, boots),
        ("RightFoot", 0.075, boots),
    ]
    for name, radius, mat in segments:
        bone = bones[name]
        legacy.weighted_cylinder(
            arm,
            "Review_" + name,
            name,
            bone.head_local,
            bone.tail_local,
            radius,
            mat,
        )


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
        "root": [round(motion_root.location.x, 6), round(motion_root.location.z, 6)],
        "joints": {name: legacy.vector(point) for name, point in joints.items()},
        "armJointContractError": errors,
        "maxArmJointContractError": max(errors.values()),
        "leftElbowAngleDeg": bend_angle(
            joints["leftShoulder"], joints["leftElbow"], joints["leftWrist"]
        ),
        "rightElbowAngleDeg": bend_angle(
            joints["rightShoulder"], joints["rightElbow"], joints["rightWrist"]
        ),
        "leftArmExtension": round(
            (joints["leftWrist"] - joints["leftShoulder"]).length, 6
        ),
        "rightArmExtension": round(
            (joints["rightWrist"] - joints["rightShoulder"]).length, 6
        ),
        "leftKneeAngleDeg": bend_angle(
            joints["leftHip"], joints["leftKnee"], joints["leftAnkle"]
        ),
        "rightKneeAngleDeg": bend_angle(
            joints["rightHip"], joints["rightKnee"], joints["rightAnkle"]
        ),
        "stanceWidth": round(abs(joints["leftAnkle"].x - joints["rightAnkle"].x), 6),
        "swordGrip": legacy.vector(sword_grip),
        "swordTip": legacy.vector(sword_tip),
        "projectedSwordLengthXZ": round(
            math.hypot(sword_tip.x - sword_grip.x, sword_tip.z - sword_grip.z), 6
        ),
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
    sword = legacy.build_sword()
    legacy.setup_scene(source["canvas"])
    scene = bpy.context.scene
    configure_fast_render(scene)
    scene.frame_start = min(review_frames)
    scene.frame_end = max(review_frames)

    for name in ("LeftForeArm", "RightForeArm"):
        arm.pose.bones[name].constraints[f"ReferenceIK_{name}"].influence = 0.0

    for frame in review_frames:
        print(f"KEYPOSE_SOLVE_START F{frame}", flush=True)
        base = ref_by_frame[frame]
        legacy.key_pose(motion_root, arm, targets, sword, base)
        joint_pose = joint_contract["poses"][str(frame)]
        if "rootOverride" in joint_pose:
            root_x, root_z = joint_pose["rootOverride"]
            motion_root.location = (float(root_x), 0.0, float(root_z))
            motion_root.keyframe_insert(data_path="location", frame=frame)
        bpy.context.view_layer.update()
        apply_arm_pose(arm, sword, joint_pose, frame=frame)
        print(f"KEYPOSE_SOLVE_OK F{frame}", flush=True)

    for owner in [motion_root, arm, sword, *targets.values()]:
        legacy.configure_interpolation(owner, set(review_frames))

    debug = {
        "action": source["action"],
        "mode": "fast-keypose-review",
        "reviewFrames": review_frames,
        "rig": arm.name,
        "armControl": "deterministic_joint_fk",
        "legControl": "ik_with_explicit_knee_poles",
        "torsoControl": "fk",
        "weaponBinding": joint_contract["weaponBinding"],
        "samples": [
            sample_frame(
                motion_root,
                arm,
                sword,
                frame,
                joint_contract["poses"][str(frame)],
            )
            for frame in review_frames
        ],
    }
    (output / "motion_debug.json").write_text(
        json.dumps(debug, indent=2) + "\n", encoding="utf-8"
    )
    (output / "arm_joint_contract.json").write_text(
        json.dumps(joint_contract, indent=2) + "\n", encoding="utf-8"
    )

    scene.frame_set(review_frames[0])
    bpy.ops.wm.save_as_mainfile(filepath=str((output / "source.blend").resolve()))

    frame_dir = output / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    for frame in review_frames:
        print(f"KEYPOSE_RENDER_START F{frame}", flush=True)
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        scene.render.filepath = str((frame_dir / f"{frame:02d}.png").resolve())
        bpy.ops.render.render(write_still=True)
        print(f"KEYPOSE_RENDER_OK F{frame}", flush=True)

    print(f"anim2sheet key-pose Blender render OK: {review_frames}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
