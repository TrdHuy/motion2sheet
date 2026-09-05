from __future__ import annotations

from pathlib import Path

import bpy
from mathutils import Matrix

from motion2sheet.motion.roundtrip.blender_common import integer_action_range


def _export_selected_armature(
    armature: bpy.types.Object,
    output: Path,
    *,
    bake_anim_use_all_actions: bool,
) -> None:
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
        bake_anim_use_all_actions=bake_anim_use_all_actions,
        bake_anim_force_startend_keying=True,
        bake_anim_step=1.0,
        bake_anim_simplify_factor=0.0,
    )


def export_armature_only_fbx(armature: bpy.types.Object, output: Path) -> None:
    """Export a deterministic armature-only FBX for Level-1 Mixamo canonicalization.

    This legacy PR12 helper exports the active Action directly. Keep it for existing
    regression paths. New canonical-rest motion normalization uses
    `export_action_with_static_rest_fbx` below so the current evaluated first pose can
    never become static FBX rest authority.
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
    _export_selected_armature(armature, output, bake_anim_use_all_actions=False)


def export_action_with_static_rest_fbx(
    armature: bpy.types.Object,
    action: bpy.types.Action,
    output: Path,
) -> None:
    """Export one stored Action while static FBX transforms stay at canonical rest.

    Blender's FBX exporter can derive static bone transforms from the currently
    evaluated pose. Therefore an active Action evaluated at its first frame risks
    folding that first motion pose into the imported rest representation. For the
    canonical Level-1 path we detach the Action, explicitly set every pose basis to
    identity, then ask Blender to bake the sole compatible stored Action through its
    `all_actions` path. Static authority is consequently the armature EditBone rest;
    animation remains the stored Action. No source/first frame is sampled as rest.
    """

    start, end = integer_action_range(action)
    scene = bpy.context.scene
    scene.frame_start = start
    scene.frame_end = end
    if armature.animation_data is None:
        armature.animation_data_create()
    previous_action = armature.animation_data.action
    if previous_action is not action:
        raise RuntimeError("canonical-rest FBX export requires the supplied Action to be active before detaching")

    # The caller must isolate bpy.data.actions to this one compatible motion Action.
    compatible_actions = [candidate for candidate in bpy.data.actions if candidate is action]
    if len(compatible_actions) != 1 or len(bpy.data.actions) != 1:
        raise RuntimeError(
            "canonical-rest FBX export requires exactly one Action datablock; "
            f"found {[candidate.name for candidate in bpy.data.actions]}"
        )

    armature.animation_data.action = None
    for pose_bone in armature.pose.bones:
        pose_bone.rotation_mode = "QUATERNION"
        pose_bone.matrix_basis = Matrix.Identity(4)
    scene.frame_set(start)
    bpy.context.view_layer.update()
    try:
        _export_selected_armature(armature, output, bake_anim_use_all_actions=True)
    finally:
        armature.animation_data.action = action
        scene.frame_set(start)
        bpy.context.view_layer.update()
