"""Blender-native Gale Slash POC: procedural swordsman motion, render and save source.blend."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def argv():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def add_bone(eb, name, head, tail, parent=None):
    bone = eb.new(name)
    bone.head = head
    bone.tail = tail
    if parent:
        bone.parent = parent
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


def weighted_cylinder(armature, name, bone_name, head, tail, radius, mat, vertices=12):
    a, b = Vector(head), Vector(tail)
    d = b - a
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=d.length, location=(a + b) * 0.5)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj.data.materials.append(mat)
    group = obj.vertex_groups.new(name=bone_name)
    group.add(range(len(obj.data.vertices)), 1.0, "REPLACE")
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = armature
    return obj


def weighted_sphere(armature, name, bone_name, center, radius, mat):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=radius, location=center)
    obj = bpy.context.object
    obj.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj.data.materials.append(mat)
    group = obj.vertex_groups.new(name=bone_name)
    group.add(range(len(obj.data.vertices)), 1.0, "REPLACE")
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = armature
    return obj


def controller_cylinder(parent, name, z0, z1, radius, mat, vertices=12):
    center = (z0 + z1) * 0.5
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=z1 - z0, location=(0, 0, center))
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    obj.parent = parent
    return obj


def build_rig():
    arm_data = bpy.data.armatures.new("GameHumanoidV1")
    arm = bpy.data.objects.new("GameHumanoidV1", arm_data)
    bpy.context.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm_data.edit_bones

    hips = add_bone(eb, "Hips", (0, 0, 0.98), (0, 0, 1.18))
    spine = add_bone(eb, "Spine", (0, 0, 1.18), (0, 0, 1.55), hips)
    neck = add_bone(eb, "Neck", (0, 0, 1.55), (0, 0, 1.70), spine)
    add_bone(eb, "Head", (0, 0, 1.70), (0, 0, 1.93), neck)

    ls = add_bone(eb, "LeftShoulder", (0, 0, 1.53), (-0.18, 0, 1.53), spine)
    lua = add_bone(eb, "LeftUpperArm", (-0.18, 0, 1.53), (-0.47, 0, 1.42), ls)
    lfa = add_bone(eb, "LeftForeArm", (-0.47, 0, 1.42), (-0.69, 0, 1.25), lua)
    add_bone(eb, "LeftHand", (-0.69, 0, 1.25), (-0.78, 0, 1.18), lfa)

    rs = add_bone(eb, "RightShoulder", (0, 0, 1.53), (0.18, 0, 1.53), spine)
    rua = add_bone(eb, "RightUpperArm", (0.18, 0, 1.53), (0.47, 0, 1.42), rs)
    rfa = add_bone(eb, "RightForeArm", (0.47, 0, 1.42), (0.69, 0, 1.25), rua)
    add_bone(eb, "RightHand", (0.69, 0, 1.25), (0.78, 0, 1.18), rfa)

    lt = add_bone(eb, "LeftUpLeg", (-0.16, 0, 0.98), (-0.18, 0, 0.56), hips)
    ll = add_bone(eb, "LeftLeg", (-0.18, 0, 0.56), (-0.18, 0, 0.15), lt)
    add_bone(eb, "LeftFoot", (-0.18, 0, 0.15), (-0.18, -0.22, 0.08), ll)
    rt = add_bone(eb, "RightUpLeg", (0.16, 0, 0.98), (0.18, 0, 0.56), hips)
    rl = add_bone(eb, "RightLeg", (0.18, 0, 0.56), (0.18, 0, 0.15), rt)
    add_bone(eb, "RightFoot", (0.18, 0, 0.15), (0.18, -0.22, 0.08), rl)

    bpy.ops.object.mode_set(mode="POSE")
    for bone in arm.pose.bones:
        bone.rotation_mode = "XYZ"
    bpy.ops.object.mode_set(mode="OBJECT")
    return arm


def build_character(arm):
    cloth = material("Cloth", (0.07, 0.15, 0.30))
    skin = material("Skin", (0.72, 0.48, 0.32))
    boots = material("Boots", (0.055, 0.04, 0.035))
    bones = arm.data.bones
    for name, radius, mat in [
        ("Spine", 0.18, cloth),
        ("LeftUpperArm", 0.075, cloth), ("LeftForeArm", 0.065, skin),
        ("RightUpperArm", 0.075, cloth), ("RightForeArm", 0.065, skin),
        ("LeftUpLeg", 0.105, cloth), ("LeftLeg", 0.085, boots),
        ("RightUpLeg", 0.105, cloth), ("RightLeg", 0.085, boots),
        ("LeftFoot", 0.08, boots), ("RightFoot", 0.08, boots),
    ]:
        b = bones[name]
        weighted_cylinder(arm, f"Body_{name}", name, b.head_local, b.tail_local, radius, mat)
    weighted_sphere(arm, "HeadMesh", "Head", (0, 0, 1.82), 0.15, skin)
    weighted_sphere(arm, "PelvisMesh", "Hips", (0, 0, 1.07), 0.19, cloth)
    weighted_sphere(arm, "LeftHandMesh", "LeftHand", (-0.735, 0, 1.215), 0.075, skin)
    weighted_sphere(arm, "RightHandMesh", "RightHand", (0.735, 0, 1.215), 0.075, skin)


def build_sword_and_ik(arm):
    steel = material("Steel", (0.55, 0.62, 0.70), 0.75)
    grip_mat = material("Grip", (0.12, 0.055, 0.025), 0.10)
    ctrl = bpy.data.objects.new("SwordController", None)
    bpy.context.collection.objects.link(ctrl)
    ctrl.rotation_mode = "XYZ"
    controller_cylinder(ctrl, "SwordGrip", -0.05, 0.23, 0.045, grip_mat)
    controller_cylinder(ctrl, "SwordBlade", 0.22, 1.18, 0.035, steel)

    right_grip = bpy.data.objects.new("RightGripTarget", None)
    left_grip = bpy.data.objects.new("LeftGripTarget", None)
    bpy.context.collection.objects.link(right_grip)
    bpy.context.collection.objects.link(left_grip)
    right_grip.parent = ctrl
    left_grip.parent = ctrl
    right_grip.location = (0, 0, 0.01)
    left_grip.location = (0, 0, 0.16)

    pole_r = bpy.data.objects.new("RightElbowPole", None)
    pole_l = bpy.data.objects.new("LeftElbowPole", None)
    bpy.context.collection.objects.link(pole_r)
    bpy.context.collection.objects.link(pole_l)
    pole_r.parent = arm
    pole_l.parent = arm
    pole_r.location = (0.62, -0.65, 1.30)
    pole_l.location = (-0.62, -0.65, 1.30)

    rik = arm.pose.bones["RightForeArm"].constraints.new("IK")
    rik.name = "TwoHandSwordIK.R"
    rik.target = right_grip
    rik.pole_target = pole_r
    rik.chain_count = 2
    rik.iterations = 64
    lik = arm.pose.bones["LeftForeArm"].constraints.new("IK")
    lik.name = "TwoHandSwordIK.L"
    lik.target = left_grip
    lik.pole_target = pole_l
    lik.chain_count = 2
    lik.iterations = 64
    return ctrl


def key_bone_y(arm, bone_name, degrees, frame):
    bone = arm.pose.bones[bone_name]
    bone.rotation_euler.y = math.radians(degrees)
    bone.keyframe_insert(data_path="rotation_euler", frame=frame)


def key_body(arm, frame, root_x, root_z, hips, spine, head, left_thigh, left_shin, right_thigh, right_shin):
    bpy.context.scene.frame_set(frame)
    arm.location.x = root_x
    arm.location.z = root_z
    arm.keyframe_insert(data_path="location", frame=frame)
    for name, degrees in {
        "Hips": hips, "Spine": spine, "Head": head,
        "LeftUpLeg": left_thigh, "LeftLeg": left_shin,
        "RightUpLeg": right_thigh, "RightLeg": right_shin,
    }.items():
        key_bone_y(arm, name, degrees, frame)


def key_sword(ctrl, frame, x, z, angle_deg):
    bpy.context.scene.frame_set(frame)
    ctrl.location = (x, -0.03, z)
    ctrl.rotation_euler = (0, math.radians(angle_deg), 0)
    ctrl.keyframe_insert(data_path="location", frame=frame)
    ctrl.keyframe_insert(data_path="rotation_euler", frame=frame)


def animate(arm, sword, frames):
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = frames
    body_keys = [
        (1,  0.00,  0.00,   0,   0,   0,  -8,  10,   8, -10),
        (3,  0.00, -0.035,  -6, -10,   5, -12,  18,  12, -14),
        (4,  0.00, -0.080, -13, -18,   8, -18,  27,  17, -21),
        (6,  0.07, -0.065,  -4, -10,   5, -28,  35,  13, -18),
        (7,  0.13, -0.045,   7,   3,  -2, -34,  39,  10, -15),
        (8,  0.21, -0.030,  15,  15,  -7, -36,  40,   8, -13),
        (9,  0.28, -0.020,  22,  26, -10, -37,  41,   7, -11),
        (10, 0.34, -0.010,  29,  34, -13, -35,  38,   5,  -8),
        (12, 0.40, -0.030,  33,  39, -15, -29,  31,   8, -11),
        (13, 0.42, -0.045,  28,  34, -12, -24,  27,  10, -13),
        (16, 0.38, -0.015,   4,   6,  -2, -12,  16,   9, -12),
    ]
    for row in body_keys:
        key_body(arm, *row)

    sword_keys = [
        (1,  0.10, 1.27,  46),
        (3,  0.21, 1.27,  58),
        (4,  0.31, 1.30,  72),
        (6,  0.32, 1.28,  78),
        (7,  0.28, 1.25,  70),
        (8,  0.18, 1.23,  30),
        (9,  0.02, 1.20, -38),
        (10, -0.10, 1.16, -78),
        (12, -0.10, 1.10, -108),
        (13, -0.03, 1.12, -92),
        (16,  0.20, 1.24,  38),
    ]
    by_frame = {row[0]: row for row in body_keys}
    for frame, x, z, angle in sword_keys:
        body = by_frame[frame]
        key_sword(sword, frame, x + body[1], z + body[2], angle)

    for owner in (arm, sword):
        action = owner.animation_data.action
        action.name = "GaleSlashBody" if owner is arm else "GaleSlashSword"
        for curve in action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = "BEZIER"
                point.handle_left_type = "AUTO_CLAMPED"
                point.handle_right_type = "AUTO_CLAMPED"
                if 7 <= point.co.x <= 10:
                    point.interpolation = "LINEAR"


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
    if getattr(scene, "eevee", None) is not None:
        scene.eevee.taa_render_samples = 8
    bpy.ops.object.light_add(type="AREA", location=(0, -4, 5))
    light = bpy.context.object
    light.data.energy = 700
    light.data.shape = "DISK"
    light.data.size = 5
    bpy.ops.object.camera_add(location=(0.18, -7.5, 2.30))
    cam = bpy.context.object
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 3.65
    direction = Vector((0.18, 0, 1.10)) - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    scene.world.color = (0.035, 0.035, 0.035)


def bone_tail_world(arm, name):
    return arm.matrix_world @ arm.pose.bones[name].tail


def sample_debug(arm, sword, frames):
    samples = []
    for frame in range(1, frames + 1):
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        tip = sword.matrix_world @ Vector((0, 0, 1.18))
        left_ankle = bone_tail_world(arm, "LeftLeg")
        right_ankle = bone_tail_world(arm, "RightLeg")
        samples.append({
            "frame": frame,
            "rootX": round(arm.location.x, 6),
            "rootZ": round(arm.location.z, 6),
            "swordTip": [round(tip.x, 6), round(tip.y, 6), round(tip.z, 6)],
            "leftAnkle": [round(left_ankle.x, 6), round(left_ankle.z, 6)],
            "rightAnkle": [round(right_ankle.x, 6), round(right_ankle.z, 6)],
        })
    return samples


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--output", required=True)
    args, _ = parser.parse_known_args(argv())
    source = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    output = Path(args.output)
    frames = int(source["frames"])
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    arm = build_rig()
    build_character(arm)
    sword = build_sword_and_ik(arm)
    animate(arm, sword, frames)
    setup_scene(source["canvas"])
    debug = {"action": source["action"], "samples": sample_debug(arm, sword, frames)}
    (output / "motion_debug.json").write_text(json.dumps(debug, indent=2) + "\n", encoding="utf-8")
    bpy.context.scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str((output / "source.blend").resolve()))
    frame_dir = output / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    for frame in range(1, frames + 1):
        bpy.context.scene.frame_set(frame)
        bpy.context.scene.render.filepath = str((frame_dir / f"{frame:02d}.png").resolve())
        bpy.ops.render.render(write_still=True)
    print(f"anim2sheet Blender render OK: {frames} frames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
