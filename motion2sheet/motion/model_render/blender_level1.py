from __future__ import annotations

from pathlib import Path

import bpy

from motion2sheet.motion.roundtrip.blender_common import integer_action_range


def export_armature_only_fbx(armature: bpy.types.Object, output: Path) -> None:
    """Export a deterministic armature-only FBX for Level-1 Mixamo canonicalization.

    This intentionally contains no mesh/skin authority. It is used only to
    remove importer-level non-TRS floating-point rest shear before the locked
    Contract B rig exporter consumes the armature.

    Blender's FBX exporter bakes the current scene frame range when exporting
    only the active action. Real Mixamo imports can leave the scene range at an
    unrelated default such as 2..251 even though the active action is 1..32, so
    pin the scene range to the exact integer action range before exporting.
    """
    if armature.animation_data is None or armature.animation_data.action is None:
        raise RuntimeError("Level-1 armature-only FBX export requires one active action")
    action = armature.animation_data.action
    start, end = integer_action_range(action)
    scene = bpy.context.scene
    scene.frame_start = start
    scene.frame_end = end
    scene.frame_set(start)
    bpy.context.view_layer.update()

    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.export_scene.fbx(
        filepath=str(output),
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
