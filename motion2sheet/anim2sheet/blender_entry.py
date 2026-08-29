"""Blender-native full-body Gale Slash POC.

Builds GameHumanoidV2, applies the v2 full-body motion contract using hybrid
FK + IK, saves authoritative source.blend, renders proxy object frames, and
writes evaluated post-IK diagnostics. Skeleton inspection is handled separately
by blender_skeleton_viewport.py from the saved blend.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


BODY_FIELDS = {
    "Pelvis": ("pelvisYawDeg", "pelvisLeanDeg"),
    "Spine": ("spineYawDeg", "spineLeanDeg"),
    "Chest": ("chestYawDeg", "chestLeanDeg"),
    "Head": ("headYawDeg", "headLeanDeg"),
}
TARGET_NAMES = (
    "leftWrist", "rightWrist", "leftAnkle", "rightAnkle",
    "leftElbowGuide", "rightElbowGuide", "leftKneeGuide", "rightKneeGuide",
)


def argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def add_bone(edit_bones, name, head, tail, parent=None, *, connected=False, deform=True):
    bone = edit_bones.new(name)
    bone.head = head
    bone.tail = tail
    bone.use_deform = deform
    if parent is not None:
        bone.parent = parent
        bone.use_connect = connected
    return bone


def material(name, color, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1.0)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.55
    bsdf.inputs["Metallic"].default_value = metallic
    return mat


def weighted_cylinder(arm, name, bone_name, head, tail, radius, mat):
    a, b = Vector(head), Vector(tail)
    direction = b - a
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=12, radius=radius, depth=direction.length, location=(a + b) * 0.5
    )
    obj = bpy.context.object
    obj.name = name
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(direction.normalized())
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj.data.materials.append(mat)
    group = obj.vertex_groups.new(name=bone_name)
    group.add(range(len(obj.data.vertices)), 1.0, "REPLACE")
    modifier = obj.modifiers.new("Armature", "ARMATURE")
    modifier.object = arm


def weighted_sphere(arm, name, bone_name, center, radius, mat):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=radius, location=center)
    obj = bpy.context.object
    obj.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj.data.materials.append(mat)
    group = obj.vertex_groups.new(name=bone_name)
    group.add(range(len(obj.data.vertices)), 1.0, "REPLACE")
    modifier = obj.modifiers.new("Armature", "ARMATURE")
    modifier.object = arm


def controller_cylinder(parent, name, z0, z1, radius, mat):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=12, radius=radius, depth=z1 - z0, location=(0, 0, (z0 + z1) * 0.5)
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    obj.parent = parent


def build_root_and_rig():
    motion_root = bpy.data.objects.new("MotionRoot", None)
    bpy.context.collection.objects.link(motion_root)

    data = bpy.data.armatures.new("GameHumanoidV2")
    arm = bpy.data.objects.new("GameHumanoidV2", data)
    bpy.context.collection.objects.link(arm)
    arm.parent = motion_root

    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = data.edit_bones

    root = add_bone(eb, "Root", (0, 0, 0.84), (0, 0, 0.96), deform=False)
    pelvis = add_bone(eb, "Pelvis", (0, 0, 0.96), (0, 0, 1.12), root, connected=True)
    spine = add_bone(eb, "Spine", (0, 0, 1.12), (0, 0, 1.34), pelvis, connected=True)
    chest = add_bone(eb, "Chest", (0, 0, 1.34), (0, 0, 1.56), spine, connected=True)
    neck = add_bone(eb, "Neck", (0, 0, 1.56), (0, 0, 1.70), chest, connected=True)
    add_bone(eb, "Head", (0, 0, 1.70), (0, 0, 1.94), neck, connected=True)

    left_clav = add_bone(eb, "LeftClavicle", (0, 0, 1.53), (-0.18, 0, 1.53), chest)
    left_upper = add_bone(
        eb, "LeftUpperArm", (-0.18, 0, 1.53), (-0.48, 0, 1.42), left_clav, connected=True
    )
    left_fore = add_bone(
        eb, "LeftForeArm", (-0.48, 0, 1.42), (-0.72, 0, 1.24), left_upper, connected=True
    )
    add_bone(
        eb, "LeftHand", (-0.72, 0, 1.24), (-0.82, 0, 1.17), left_fore, connected=True
    )

    right_clav = add_bone(eb, "RightClavicle", (0, 0, 1.53), (0.18, 0, 1.53), chest)
    right_upper = add_bone(
        eb, "RightUpperArm", (0.18, 0, 1.53), (0.48, 0, 1.42), right_clav, connected=True
    )
    right_fore = add_bone(
        eb, "RightForeArm", (0.48, 0, 1.42), (0.72, 0, 1.24), right_upper, connected=True
    )
    add_bone(
        eb, "RightHand", (0.72, 0, 1.24), (0.82, 0, 1.17), right_fore, connected=True
    )

    left_hip = add_bone(
        eb, "LeftHip", (0, 0, 1.03), (-0.17, 0, 0.96), pelvis, deform=False
    )
    left_thigh = add_bone(
        eb, "LeftThigh", (-0.17, 0, 0.96), (-0.23, 0, 0.56), left_hip, connected=True
    )
    left_shin = add_bone(
        eb, "LeftShin", (-0.23, 0, 0.56), (-0.30, 0, 0.14), left_thigh, connected=True
    )
    add_bone(
        eb, "LeftFoot", (-0.30, 0, 0.14), (-0.30, -0.24, 0.07), left_shin, connected=True
    )

    right_hip = add_bone(
        eb, "RightHip", (0, 0, 1.03), (0.17, 0, 0.96), pelvis, deform=False
    )
    right_thigh = add_bone(
        eb, "RightThigh", (0.17, 0, 0.96), (0.23, 0, 0.56), right_hip, connected=True
    )
    right_shin = add_bone(
        eb, "RightShin", (0.23, 0, 0.56), (0.30, 0, 0.14), right_thigh, connected=True
    )
    add_bone(
        eb, "RightFoot", (0.30, 0, 0.14), (0.30, -0.24, 0.07), right_shin, connected=True
    )

    bpy.ops.object.mode_set(mode="POSE")
    for bone in arm.pose.bones:
        bone.rotation_mode = "XYZ"
    bpy.ops.object.mode_set(mode="OBJECT")
    return motion_root, arm


def build_character(arm):
    cloth = material("Cloth", (0.07, 0.15, 0.30))
    skin = material("Skin", (0.72, 0.48, 0.32))
    boots = material("Boots", (0.055, 0.04, 0.035))
    bones = arm.data.bones
    segments = [
        ("Spine", 0.15, cloth), ("Chest", 0.18, cloth),
        ("LeftUpperArm", 0.08, cloth), ("LeftForeArm", 0.07, skin),
        ("RightUpperArm", 0.08, cloth), ("RightForeArm", 0.07, skin),
        ("LeftThigh", 0.11, cloth), ("LeftShin", 0.09, boots),
        ("RightThigh", 0.11, cloth), ("RightShin", 0.09, boots),
    ]
    for name, radius, mat in segments:
        bone = bones[name]
        weighted_cylinder(
            arm, "Body_" + name, name, bone.head_local, bone.tail_local, radius, mat
        )
    weighted_sphere(arm, "HeadMesh", "Head", (0, 0, 1.82), 0.15, skin)
    weighted_sphere(arm, "PelvisMesh", "Pelvis", (0, 0, 1.04), 0.20, cloth)
    joints = [
        ("LeftUpperArm", (-0.18, 0, 1.53), 0.085, skin),
        ("RightUpperArm", (0.18, 0, 1.53), 0.085, skin),
        ("LeftForeArm", (-0.48, 0, 1.42), 0.075, skin),
        ("RightForeArm", (0.48, 0, 1.42), 0.075, skin),
        ("LeftHand", (-0.77, 0, 1.205), 0.075, skin),
        ("RightHand", (0.77, 0, 1.205), 0.075, skin),
        ("LeftShin", (-0.23, 0, 0.56), 0.095, cloth),
        ("RightShin", (0.23, 0, 0.56), 0.095, cloth),
    ]
    for name, center, radius, mat in joints:
        weighted_sphere(arm, "Joint_" + name, name, center, radius, mat)


def empty(name):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    return obj


def build_pose_targets(arm):
    targets = {name: empty(name[0].upper() + name[1:] + "Target") for name in TARGET_NAMES}
    chains = [
        ("LeftForeArm", "leftWrist", "leftElbowGuide"),
        ("RightForeArm", "rightWrist", "rightElbowGuide"),
        ("LeftShin", "leftAnkle", "leftKneeGuide"),
        ("RightShin", "rightAnkle", "rightKneeGuide"),
    ]
    for bone_name, target_name, guide_name in chains:
        ik = arm.pose.bones[bone_name].constraints.new("IK")
        ik.name = "ReferenceIK_" + bone_name
        ik.target = targets[target_name]
        ik.pole_target = targets[guide_name]
        ik.chain_count = 2
        ik.iterations = 64
    return targets


def build_sword():
    steel = material("Steel", (0.55, 0.62, 0.70), 0.75)
    grip_mat = material("Grip", (0.12, 0.055, 0.025), 0.10)
    ctrl = empty("SwordController")
    ctrl.rotation_mode = "QUATERNION"
    controller_cylinder(ctrl, "SwordGrip", -0.08, 0.24, 0.045, grip_mat)
    controller_cylinder(ctrl, "SwordBlade", 0.23, 1.20, 0.035, steel)
    return ctrl


def set_trunk_rotation(pose_bone, yaw_deg, lean_deg):
    pose_bone.rotation_euler = (
        0.0,
        math.radians(float(yaw_deg)),
        math.radians(-float(lean_deg)),
    )


def key_pose(motion_root, arm, targets, sword, row):
    frame = int(row["frame"])
    bpy.context.scene.frame_set(frame)
    root_x, root_z = row["root"]
    motion_root.location = (float(root_x), 0.0, float(root_z))
    motion_root.keyframe_insert(data_path="location", frame=frame)

    body = row["body"]
    for bone_name, (yaw_key, lean_key) in BODY_FIELDS.items():
        set_trunk_rotation(arm.pose.bones[bone_name], body[yaw_key], body[lean_key])
        arm.pose.bones[bone_name].keyframe_insert(data_path="rotation_euler", frame=frame)

    arm.pose.bones["LeftClavicle"].rotation_euler.z = math.radians(
        float(body["leftClavicleSwingDeg"])
    )
    arm.pose.bones["RightClavicle"].rotation_euler.z = math.radians(
        -float(body["rightClavicleSwingDeg"])
    )
    arm.pose.bones["LeftClavicle"].keyframe_insert(data_path="rotation_euler", frame=frame)
    arm.pose.bones["RightClavicle"].keyframe_insert(data_path="rotation_euler", frame=frame)

    row_targets = row["targets"]
    for name in TARGET_NAMES:
        targets[name].location = Vector(row_targets[name])
        targets[name].keyframe_insert(data_path="location", frame=frame)

    grip = Vector(row_targets["swordGrip"])
    tip_guide = Vector(row_targets["swordTipGuide"])
    direction = tip_guide - grip
    if direction.length < 1e-6:
        raise RuntimeError(f"frame {frame}: sword grip/tip guide are coincident")
    sword.location = grip
    sword.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(direction.normalized())
    sword.keyframe_insert(data_path="location", frame=frame)
    sword.keyframe_insert(data_path="rotation_quaternion", frame=frame)


def configure_interpolation(owner, strike_frames):
    action = owner.animation_data.action if owner.animation_data else None
    if not action:
        return
    for curve in action.fcurves:
        for point in curve.keyframe_points:
            frame = int(round(point.co.x))
            point.interpolation = "LINEAR" if frame in strike_frames else "BEZIER"
            point.handle_left_type = "AUTO_CLAMPED"
            point.handle_right_type = "AUTO_CLAMPED"


def animate_from_reference(motion_root, arm, targets, sword, reference, frames):
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = frames
    poses = reference["keyPoses"]
    if len(poses) != frames:
        raise RuntimeError(f"reference key pose count {len(poses)} != frames {frames}")
    for row in poses:
        key_pose(motion_root, arm, targets, sword, row)

    strike_frames = set(int(value) for value in reference["solver"]["strikeFrames"])
    for owner in [motion_root, arm, sword, *targets.values()]:
        configure_interpolation(owner, strike_frames)


def setup_scene(canvas):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.film_transparent = True
    scene.render.resolution_x = int(canvas[0])
    scene.render.resolution_y = int(canvas[1])
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.view_settings.look = "AgX - Medium High Contrast"

    bpy.ops.object.light_add(type="AREA", location=(0, -4, 5))
    light = bpy.context.object
    light.data.energy = 700
    light.data.size = 5

    bpy.ops.object.camera_add(location=(0.18, -7.5, 2.25))
    camera = bpy.context.object
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 3.55
    direction = Vector((0.18, 0, 1.08)) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    scene.camera = camera
    scene.world.color = (0.035, 0.035, 0.035)


def bone_head_world(arm, name):
    return arm.matrix_world @ arm.pose.bones[name].head


def bone_tail_world(arm, name):
    return arm.matrix_world @ arm.pose.bones[name].tail


def vector(values):
    return [round(float(value), 6) for value in values]


def line_yaw_deg(left, right):
    delta = right - left
    return round(math.degrees(math.atan2(delta.y, delta.x)), 6)


def bend_angle_deg(a, joint, c):
    u = (a - joint).normalized()
    v = (c - joint).normalized()
    dot = max(-1.0, min(1.0, float(u.dot(v))))
    return round(math.degrees(math.acos(dot)), 6)


def sample_debug(motion_root, arm, targets, sword, reference, frames):
    phases = {int(row["frame"]): row["phase"] for row in reference["keyPoses"]}
    samples = []
    for frame in range(1, frames + 1):
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()

        joints = {
            "leftShoulder": bone_head_world(arm, "LeftUpperArm"),
            "leftElbow": bone_tail_world(arm, "LeftUpperArm"),
            "leftWrist": bone_tail_world(arm, "LeftForeArm"),
            "rightShoulder": bone_head_world(arm, "RightUpperArm"),
            "rightElbow": bone_tail_world(arm, "RightUpperArm"),
            "rightWrist": bone_tail_world(arm, "RightForeArm"),
            "leftHip": bone_head_world(arm, "LeftThigh"),
            "leftKnee": bone_tail_world(arm, "LeftThigh"),
            "leftAnkle": bone_tail_world(arm, "LeftShin"),
            "rightHip": bone_head_world(arm, "RightThigh"),
            "rightKnee": bone_tail_world(arm, "RightThigh"),
            "rightAnkle": bone_tail_world(arm, "RightShin"),
        }

        sword_grip = sword.matrix_world @ Vector((0, 0, 0))
        sword_tip = sword.matrix_world @ Vector((0, 0, 1.20))
        ik_error = {}
        for name in ("leftWrist", "rightWrist", "leftAnkle", "rightAnkle"):
            ik_error[name] = round(
                (joints[name] - targets[name].matrix_world.translation).length, 6
            )

        samples.append({
            "frame": frame,
            "phase": phases[frame],
            "root": [round(motion_root.location.x, 6), round(motion_root.location.z, 6)],
            "joints": {name: vector(point) for name, point in joints.items()},
            "pelvisYawDeg": line_yaw_deg(joints["leftHip"], joints["rightHip"]),
            "shoulderYawDeg": line_yaw_deg(
                joints["leftShoulder"], joints["rightShoulder"]
            ),
            "swordGrip": vector(sword_grip),
            "swordTip": vector(sword_tip),
            "projectedSwordLengthXZ": round(
                math.hypot(
                    sword_tip.x - sword_grip.x,
                    sword_tip.z - sword_grip.z,
                ),
                6,
            ),
            "ikError": ik_error,
            "stanceWidth": round(
                abs(joints["leftAnkle"].x - joints["rightAnkle"].x), 6
            ),
            "leftArmExtension": round(
                (joints["leftShoulder"] - joints["leftWrist"]).length, 6
            ),
            "rightArmExtension": round(
                (joints["rightShoulder"] - joints["rightWrist"]).length, 6
            ),
            "leftElbowAngleDeg": bend_angle_deg(
                joints["leftShoulder"], joints["leftElbow"], joints["leftWrist"]
            ),
            "rightElbowAngleDeg": bend_angle_deg(
                joints["rightShoulder"], joints["rightElbow"], joints["rightWrist"]
            ),
            "leftKneeAngleDeg": bend_angle_deg(
                joints["leftHip"], joints["leftKnee"], joints["leftAnkle"]
            ),
            "rightKneeAngleDeg": bend_angle_deg(
                joints["rightHip"], joints["rightKnee"], joints["rightAnkle"]
            ),
        })
    return samples


def validate_contract(reference, frames):
    if int(reference.get("version", 0)) < 2:
        raise RuntimeError("full-body solver requires pose reference version >= 2")
    poses = reference.get("keyPoses", [])
    if len(poses) != frames:
        raise RuntimeError(f"pose reference must contain {frames} keyPoses")

    required_body = {
        "pelvisYawDeg", "pelvisLeanDeg", "spineYawDeg", "spineLeanDeg",
        "chestYawDeg", "chestLeanDeg", "headYawDeg", "headLeanDeg",
        "leftClavicleSwingDeg", "rightClavicleSwingDeg",
    }
    required_targets = set(TARGET_NAMES) | {"swordGrip", "swordTipGuide"}
    for expected, row in enumerate(poses, start=1):
        if int(row.get("frame", -1)) != expected:
            raise RuntimeError(f"pose reference frame {expected} is missing/out of order")
        missing_body = required_body - set(row.get("body", {}))
        missing_targets = required_targets - set(row.get("targets", {}))
        if missing_body or missing_targets:
            raise RuntimeError(
                f"frame {expected}: missing body={sorted(missing_body)} "
                f"targets={sorted(missing_targets)}"
            )


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--output", required=True)
    args, _ = parser.parse_known_args(argv())

    source = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    output = Path(args.output)
    frames = int(source["frames"])
    reference = source.get("poseReferenceData")
    if not isinstance(reference, dict):
        raise RuntimeError("source spec missing embedded poseReferenceData")
    validate_contract(reference, frames)

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    motion_root, arm = build_root_and_rig()
    build_character(arm)
    targets = build_pose_targets(arm)
    sword = build_sword()
    animate_from_reference(motion_root, arm, targets, sword, reference, frames)
    setup_scene(source["canvas"])

    debug = {
        "action": source["action"],
        "rig": arm.name,
        "reference": reference.get("name"),
        "impactFrame": reference["solver"]["impactFrame"],
        "samples": sample_debug(
            motion_root, arm, targets, sword, reference, frames
        ),
    }
    (output / "motion_debug.json").write_text(
        json.dumps(debug, indent=2) + "\n", encoding="utf-8"
    )

    bpy.context.scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str((output / "source.blend").resolve()))

    frame_dir = output / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    for frame in range(1, frames + 1):
        bpy.context.scene.frame_set(frame)
        bpy.context.scene.render.filepath = str((frame_dir / f"{frame:02d}.png").resolve())
        bpy.ops.render.render(write_still=True)

    print(f"anim2sheet full-body Blender render OK: {frames} frames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
