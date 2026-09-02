from __future__ import annotations

import bpy
from mathutils import Vector

from motion2sheet.motion.roundtrip.blender_common import trs_to_matrix


def clean_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in tuple(bpy.data.armatures):
        if block.users == 0:
            bpy.data.armatures.remove(block)


def build_armature(rig: dict):
    armature_data = bpy.data.armatures.new(rig["armatureObject"]["dataName"])
    armature = bpy.data.objects.new(rig["armatureObject"]["name"], armature_data)
    bpy.context.collection.objects.link(armature)
    armature.matrix_world = trs_to_matrix(rig["armatureObject"]["transform"])
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")

    for bone_data in rig["bones"]:
        edit_bone = armature_data.edit_bones.new(bone_data["name"])
        edit_bone.head = Vector((0.0, 0.0, 0.0))
        edit_bone.tail = Vector((0.0, 1.0, 0.0))

    for bone_data in rig["bones"]:
        parent_name = bone_data["parent"]
        if parent_name:
            armature_data.edit_bones[bone_data["name"]].parent = armature_data.edit_bones[parent_name]

    for bone_data in rig["bones"]:
        edit_bone = armature_data.edit_bones[bone_data["name"]]
        geometry = bone_data["editGeometry"]
        edit_bone.head = Vector(geometry["head"])
        edit_bone.tail = Vector(geometry["tail"])
        edit_bone.roll = float(geometry["roll"])

    for bone_data in rig["bones"]:
        if bone_data["parent"]:
            armature_data.edit_bones[bone_data["name"]].use_connect = bool(
                bone_data["properties"].get("useConnect", False)
            )

    bpy.ops.object.mode_set(mode="POSE")
    bpy.ops.object.mode_set(mode="OBJECT")
    for bone_data in rig["bones"]:
        bone = armature_data.bones[bone_data["name"]]
        props = bone_data["properties"]
        bone.use_deform = bool(props.get("useDeform", True))
        bone.use_inherit_rotation = bool(props.get("useInheritRotation", True))
        bone.use_local_location = bool(props.get("useLocalLocation", True))
        if "inheritScale" in props:
            bone.inherit_scale = props["inheritScale"]
        bone.head_radius = float(props.get("headRadius", bone.head_radius))
        bone.tail_radius = float(props.get("tailRadius", bone.tail_radius))
        bone.envelope_distance = float(props.get("envelopeDistance", bone.envelope_distance))
        bone.envelope_weight = float(props.get("envelopeWeight", bone.envelope_weight))
        if hasattr(bone, "use_relative_parent") and "useRelativeParent" in props:
            bone.use_relative_parent = bool(props["useRelativeParent"])
    return armature


def build_action(armature, animation: dict):
    scene = bpy.context.scene
    scene.render.fps = int(animation["fpsNumerator"])
    scene.render.fps_base = float(animation["fpsBase"])
    start, end = animation["frameRange"]
    scene.frame_start = start
    scene.frame_end = end
    action = bpy.data.actions.new(animation["source"]["action"])
    armature.animation_data_create().action = action
    for pose_bone in armature.pose.bones:
        pose_bone.rotation_mode = "QUATERNION"
    for entry in animation["frames"]:
        frame = int(entry["frame"])
        scene.frame_set(frame)
        for bone_name, transform in entry["bones"].items():
            pose_bone = armature.pose.bones[bone_name]
            pose_bone.matrix_basis = trs_to_matrix(transform)
            pose_bone.keyframe_insert(data_path="location", frame=frame, group=bone_name)
            pose_bone.keyframe_insert(data_path="rotation_quaternion", frame=frame, group=bone_name)
            pose_bone.keyframe_insert(data_path="scale", frame=frame, group=bone_name)
    for fcurve in action.fcurves:
        for keyframe in fcurve.keyframe_points:
            keyframe.interpolation = "LINEAR"
    scene.frame_set(start)
    bpy.context.view_layer.update()
    return action


def build_json_scene(rig: dict, animation: dict):
    """Materialize the canonical rig/rest + matrix_basis motion authorities in Blender."""

    clean_scene()
    armature = build_armature(rig)
    action = build_action(armature, animation)
    return armature, action
