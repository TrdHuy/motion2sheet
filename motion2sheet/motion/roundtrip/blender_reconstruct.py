from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy
from mathutils import Vector

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from motion2sheet.motion.roundtrip.blender_common import trs_to_matrix
from motion2sheet.motion.roundtrip.schema import read_json, validate_animation_document, validate_rig_document


def _argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


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

    # Create every EditBone first so hierarchy attachment cannot reinterpret
    # already-authored source geometry. The actual source head/tail/roll are
    # restored only after all parent links exist.
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

    # Apply connectivity last. A connected source bone is expected to have a
    # head exactly at its parent's tail; Blender may snap that shared endpoint,
    # which preserves the source topology rather than inventing geometry.
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


def shift_action_frames(action, delta: float) -> None:
    for fcurve in action.fcurves:
        for keyframe in fcurve.keyframe_points:
            keyframe.co.x += delta
            keyframe.handle_left.x += delta
            keyframe.handle_right.x += delta
        fcurve.update()


def export_fbx(armature, output_path: Path) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    action = armature.animation_data.action
    scene = bpy.context.scene
    original_start = scene.frame_start
    original_end = scene.frame_end

    # Blender's legacy FBX importer applies anim_offset=1.0 by default. The
    # source FBX therefore arrives one Blender frame later than its FBX time.
    # Invert that convention only while writing FBX so a clean default re-import
    # lands back on the exact canonical source frame range.
    shift_action_frames(action, -1.0)
    scene.frame_start = original_start - 1
    scene.frame_end = original_end - 1
    try:
        bpy.ops.export_scene.fbx(
            filepath=str(output_path),
            use_selection=True,
            object_types={"ARMATURE"},
            apply_unit_scale=True,
            apply_scale_options="FBX_SCALE_NONE",
            use_space_transform=True,
            bake_space_transform=False,
            axis_forward="-Z",
            axis_up="Y",
            primary_bone_axis="Y",
            secondary_bone_axis="X",
            add_leaf_bones=False,
            use_armature_deform_only=False,
            armature_nodetype="NULL",
            bake_anim=True,
            bake_anim_use_all_bones=True,
            bake_anim_use_nla_strips=False,
            bake_anim_use_all_actions=False,
            bake_anim_force_startend_keying=True,
            bake_anim_step=1.0,
            bake_anim_simplify_factor=0.0,
        )
    finally:
        shift_action_frames(action, 1.0)
        scene.frame_start = original_start
        scene.frame_end = original_end
        scene.frame_set(original_start)
        bpy.context.view_layer.update()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rig", required=True)
    parser.add_argument("--animation", required=True)
    parser.add_argument("--blend-output", required=True)
    parser.add_argument("--fbx-output", required=True)
    args = parser.parse_args(_argv())
    rig = validate_rig_document(read_json(Path(args.rig)))
    animation = validate_animation_document(read_json(Path(args.animation)), rig)
    blend_output = Path(args.blend_output).resolve()
    fbx_output = Path(args.fbx_output).resolve()
    blend_output.parent.mkdir(parents=True, exist_ok=True)
    fbx_output.parent.mkdir(parents=True, exist_ok=True)
    clean_scene()
    armature = build_armature(rig)
    build_action(armature, animation)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_output), check_existing=False)
    export_fbx(armature, fbx_output)
    print(f"motion2sheet: JSON-only reconstruction OK -> {blend_output}; {fbx_output}")


if __name__ == "__main__":
    main()
