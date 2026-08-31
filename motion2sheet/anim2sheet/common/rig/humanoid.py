"""Reusable profile-driven humanoid construction and Blender helpers."""
from __future__ import annotations

import math

import bpy
from mathutils import Vector


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


def target_rows(rig_profile: dict) -> list[dict]:
    rows = rig_profile.get("targets", [])
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("rig profile targets missing")
    return rows


def target_object_name(rig_profile: dict, semantic: str) -> str:
    for row in target_rows(rig_profile):
        if row.get("semantic") == semantic:
            return str(row["object"])
    raise RuntimeError(f"rig profile target semantic not found: {semantic}")


def build_root_and_rig(rig_profile: dict):
    root_name = str(rig_profile.get("rootObject", "MotionRoot"))
    armature_name = str(rig_profile["name"])
    motion_root = bpy.data.objects.new(root_name, None)
    bpy.context.collection.objects.link(motion_root)
    data = bpy.data.armatures.new(armature_name)
    arm = bpy.data.objects.new(armature_name, data)
    bpy.context.collection.objects.link(arm)
    arm.parent = motion_root
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = data.edit_bones
    created = {}
    for row in rig_profile["restPose"]["bones"]:
        name = str(row["name"])
        parent_name = row.get("parent")
        parent = created.get(str(parent_name)) if parent_name else None
        if parent_name and parent is None:
            raise RuntimeError(f"rig profile bone {name} references unknown parent {parent_name}")
        created[name] = add_bone(
            eb,
            name,
            row["head"],
            row["tail"],
            parent,
            connected=bool(row.get("connected", False)),
            deform=bool(row.get("deform", True)),
        )
    bpy.ops.object.mode_set(mode="POSE")
    rotation_mode = str(rig_profile.get("rotationMode", "XYZ"))
    for bone in arm.pose.bones:
        bone.rotation_mode = rotation_mode
    bpy.ops.object.mode_set(mode="OBJECT")
    return motion_root, arm


def _build_materials(rows: list[dict]) -> dict[str, object]:
    values = {}
    for row in rows:
        values[str(row["name"])] = material(
            str(row["name"]),
            tuple(float(v) for v in row["color"]),
            float(row.get("metallic", 0.0)),
        )
    return values


def build_character(arm, character_profile: dict):
    body = character_profile["body"]
    materials = _build_materials(list(body["materials"]))
    bones = arm.data.bones
    for row in body["segments"]:
        bone_name = str(row["bone"])
        bone = bones[bone_name]
        weighted_cylinder(
            arm,
            str(row["object"]),
            bone_name,
            bone.head_local,
            bone.tail_local,
            float(row["radius"]),
            materials[str(row["material"])],
        )
    for row in body["spheres"]:
        weighted_sphere(
            arm,
            str(row["object"]),
            str(row["bone"]),
            row["center"],
            float(row["radius"]),
            materials[str(row["material"])],
        )
    return materials


def add_review_connectors(arm, character_profile: dict) -> None:
    body = character_profile["body"]
    bones = arm.data.bones
    for row in body.get("reviewConnectors", []):
        mat = bpy.data.materials.get(str(row["material"]))
        if mat is None:
            raise RuntimeError(f"proxy material missing before review connector: {row['material']}")
        bone_name = str(row["bone"])
        bone = bones[bone_name]
        weighted_cylinder(
            arm,
            str(row["object"]),
            bone_name,
            bone.head_local,
            bone.tail_local,
            float(row["radius"]),
            mat,
        )
    motion_root = arm.parent
    if motion_root is None:
        raise RuntimeError("review armature must be parented to motion root")
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH":
            obj.parent = motion_root


def build_pose_targets(arm, rig_profile: dict):
    targets = {str(row["semantic"]): empty(str(row["object"])) for row in target_rows(rig_profile)}
    for row in rig_profile["solvers"]["ikChains"]:
        bone_name = str(row["bone"])
        target_name = str(row["target"])
        guide_name = str(row["guide"])
        ik = arm.pose.bones[bone_name].constraints.new("IK")
        ik.name = str(row["constraint"])
        ik.target = targets[target_name]
        ik.pole_target = targets[guide_name]
        ik.chain_count = int(row.get("chainCount", 2))
        ik.iterations = int(row.get("iterations", 64))
    return targets


def set_trunk_rotation(pose_bone, yaw_deg, lean_deg, solver_profile: dict | None = None):
    cfg = solver_profile or {"yawAxis": "Y", "leanAxis": "Z", "leanSign": -1.0}
    values = {"X": 0.0, "Y": 0.0, "Z": 0.0}
    values[str(cfg.get("yawAxis", "Y"))] = math.radians(float(yaw_deg))
    values[str(cfg.get("leanAxis", "Z"))] = math.radians(float(lean_deg)) * float(cfg.get("leanSign", -1.0))
    pose_bone.rotation_euler = (values["X"], values["Y"], values["Z"])


def configure_interpolation(owner, authored_frames, interpolation: str = "LINEAR"):
    action = owner.animation_data.action if owner.animation_data else None
    if not action:
        return
    frame_set = set(int(v) for v in authored_frames)
    for curve in action.fcurves:
        for point in curve.keyframe_points:
            frame = int(round(point.co.x))
            point.interpolation = interpolation if frame in frame_set else "BEZIER"
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
