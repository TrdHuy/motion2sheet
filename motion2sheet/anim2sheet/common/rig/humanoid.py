"""Reusable GameHumanoidV2 construction and Blender helpers."""
from __future__ import annotations

import math

import bpy
from mathutils import Vector


TARGET_NAMES = (
    "leftWrist", "rightWrist", "leftAnkle", "rightAnkle",
    "leftElbowGuide", "rightElbowGuide", "leftKneeGuide", "rightKneeGuide",
)


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


def empty(name):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    return obj


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
    left_upper = add_bone(eb, "LeftUpperArm", (-0.18, 0, 1.53), (-0.48, 0, 1.42), left_clav, connected=True)
    left_fore = add_bone(eb, "LeftForeArm", (-0.48, 0, 1.42), (-0.72, 0, 1.24), left_upper, connected=True)
    add_bone(eb, "LeftHand", (-0.72, 0, 1.24), (-0.82, 0, 1.17), left_fore, connected=True)
    right_clav = add_bone(eb, "RightClavicle", (0, 0, 1.53), (0.18, 0, 1.53), chest)
    right_upper = add_bone(eb, "RightUpperArm", (0.18, 0, 1.53), (0.48, 0, 1.42), right_clav, connected=True)
    right_fore = add_bone(eb, "RightForeArm", (0.48, 0, 1.42), (0.72, 0, 1.24), right_upper, connected=True)
    add_bone(eb, "RightHand", (0.72, 0, 1.24), (0.82, 0, 1.17), right_fore, connected=True)
    left_hip = add_bone(eb, "LeftHip", (0, 0, 1.03), (-0.17, 0, 0.96), pelvis, deform=False)
    left_thigh = add_bone(eb, "LeftThigh", (-0.17, 0, 0.96), (-0.23, 0, 0.56), left_hip, connected=True)
    left_shin = add_bone(eb, "LeftShin", (-0.23, 0, 0.56), (-0.30, 0, 0.14), left_thigh, connected=True)
    add_bone(eb, "LeftFoot", (-0.30, 0, 0.14), (-0.30, -0.24, 0.07), left_shin, connected=True)
    right_hip = add_bone(eb, "RightHip", (0, 0, 1.03), (0.17, 0, 0.96), pelvis, deform=False)
    right_thigh = add_bone(eb, "RightThigh", (0.17, 0, 0.96), (0.23, 0, 0.56), right_hip, connected=True)
    right_shin = add_bone(eb, "RightShin", (0.23, 0, 0.56), (0.30, 0, 0.14), right_thigh, connected=True)
    add_bone(eb, "RightFoot", (0.30, 0, 0.14), (0.30, -0.24, 0.07), right_shin, connected=True)
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
        weighted_cylinder(arm, "Body_" + name, name, bone.head_local, bone.tail_local, radius, mat)
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


def add_review_connectors(arm) -> None:
    cloth = bpy.data.materials.get("Cloth")
    skin = bpy.data.materials.get("Skin")
    boots = bpy.data.materials.get("Boots")
    if cloth is None or skin is None or boots is None:
        raise RuntimeError("proxy materials missing before review connectors")
    bones = arm.data.bones
    for name, radius, mat in [
        ("Neck", 0.065, skin), ("LeftClavicle", 0.055, cloth),
        ("RightClavicle", 0.055, cloth), ("LeftHand", 0.055, skin),
        ("RightHand", 0.055, skin), ("LeftFoot", 0.075, boots),
        ("RightFoot", 0.075, boots),
    ]:
        bone = bones[name]
        weighted_cylinder(arm, "Review_" + name, name, bone.head_local, bone.tail_local, radius, mat)
    motion_root = arm.parent
    if motion_root is None:
        raise RuntimeError("review armature must be parented to MotionRoot")
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH":
            obj.parent = motion_root


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


def set_trunk_rotation(pose_bone, yaw_deg, lean_deg):
    pose_bone.rotation_euler = (0.0, math.radians(float(yaw_deg)), math.radians(-float(lean_deg)))


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


def configure_review_render(scene) -> None:
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.film_transparent = True
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = False
    scene.display.shading.show_cavity = True
    scene.display.shading.background_type = "WORLD"


def bone_head_world(arm, name):
    return arm.matrix_world @ arm.pose.bones[name].head


def bone_tail_world(arm, name):
    return arm.matrix_world @ arm.pose.bones[name].tail


def vector(values):
    return [round(float(value), 6) for value in values]
