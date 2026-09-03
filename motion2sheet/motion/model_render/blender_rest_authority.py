from __future__ import annotations

from pathlib import Path
from typing import Any

import bpy
from io_scene_fbx import parse_fbx
from mathutils import Vector

from motion2sheet.motion.extract.blender import clean_scene, find_armature, import_motion
from motion2sheet.motion.model_render.rest import character_rig_id, character_rest_fingerprint
from motion2sheet.motion.roundtrip.blender_common import (
    bone_properties,
    matrix_to_trs,
    ordered_bones,
    source_sha256,
)
from motion2sheet.motion.roundtrip.fbx import native
from motion2sheet.motion.roundtrip.schema import validate_rig_document


def import_character_fbx(path: Path) -> bpy.types.Object:
    """Import character geometry/rig without selecting or sampling an animation action."""

    clean_scene()
    import_motion(path)
    armature = find_armature()
    bpy.context.view_layer.update()
    return armature


def _static_fbx_rig_metadata(path: Path, bone_names: list[str]) -> dict[str, Any]:
    """Read only static FBX bone/global metadata; animation stacks are intentionally ignored."""

    root, version = parse_fbx.parse(str(path), use_namedtuple=True)
    table = native._node_table(root)
    requested = set(bone_names)
    models = {
        native._name(elem): elem
        for elem in table.values()
        if elem.id == b"Model" and native._name(elem) in requested
    }
    if set(models) != requested:
        missing = sorted(requested - set(models))
        raise RuntimeError(f"character FBX static metadata cannot resolve rig bone Models: {missing}")
    return {
        "fbxVersion": int(version),
        "globalSettings": native._global_settings(root),
        "bones": {
            name: {"transformStack": native._model_transform_stack(models[name])}
            for name in sorted(models)
        },
    }


def _capture_edit_rest(armature: bpy.types.Object) -> dict[str, dict[str, Any]]:
    """Capture Blender EditBone authority and its orthogonal matrix without using pose/action state."""

    if armature.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        return {
            edit_bone.name: {
                "head": [float(value) for value in edit_bone.head],
                "tail": [float(value) for value in edit_bone.tail],
                "roll": float(edit_bone.roll),
                "matrix": edit_bone.matrix.copy(),
            }
            for edit_bone in armature.data.edit_bones
        }
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")


def capture_character_rig_document(input_path: Path, armature: bpy.types.Object) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create a clip-independent character rig from FBX edit/rest data.

    `editGeometry` is the sole rest authority. The `rest` TRS fields are derived caches
    reconstructed from EditBone matrices, avoiding tiny importer shear in Bone.matrix_local
    and avoiding every animation frame/action as a rest substitute.
    """

    edit = _capture_edit_rest(armature)
    bones: list[dict[str, Any]] = []
    for bone in ordered_bones(armature):
        row = edit[bone.name]
        local_matrix = row["matrix"].copy()
        if bone.parent is not None:
            local_matrix = edit[bone.parent.name]["matrix"].inverted_safe() @ local_matrix
        head = Vector(row["head"])
        tail = Vector(row["tail"])
        bones.append(
            {
                "name": bone.name,
                "parent": bone.parent.name if bone.parent else None,
                "rest": matrix_to_trs(local_matrix, f"character edit-rest cache for bone {bone.name}"),
                "length": float((tail - head).length),
                "properties": bone_properties(bone),
                "editGeometry": {
                    "head": row["head"],
                    "tail": row["tail"],
                    "roll": row["roll"],
                },
            }
        )

    scene = bpy.context.scene
    rig: dict[str, Any] = {
        "schema": "motion2sheet.source-rig",
        "version": 1,
        "id": "character-rest-rig-v1",
        "source": {
            "format": "FBX",
            "filename": input_path.name,
            "sha256": source_sha256(input_path),
            "importer": "blender-fbx",
        },
        "coordinateSystem": {
            "space": "Blender scene after source import",
            "handedness": "right-handed",
            "rightAxis": "+X",
            "forwardAxis": "-Y",
            "upAxis": "+Z",
        },
        "units": {
            "system": str(scene.unit_settings.system),
            "metersPerBlenderUnit": float(scene.unit_settings.scale_length or 1.0),
        },
        "restAuthority": "editGeometry",
        "editGeometrySpace": "armature-local",
        "armatureObject": {
            "name": armature.name,
            "dataName": armature.data.name,
            "transform": matrix_to_trs(armature.matrix_world.copy(), "character armature object transform"),
        },
        "bones": bones,
    }
    rig["id"] = character_rig_id(rig)
    rig["sourceFormat"] = {"fbx": _static_fbx_rig_metadata(input_path, [bone["name"] for bone in bones])}
    rig = validate_rig_document(rig)
    diagnostics = {
        "mode": "fbx-bind-edit-rest-v1",
        "restAuthority": "armature-editGeometry",
        "derivedRestCache": "EditBone.matrix local TRS",
        "sourceFormatAuthority": "static-fbx-transform-stack-only",
        "animationIndependent": True,
        "animationActionRead": False,
        "animationFrameSampled": False,
        "firstAnimationPoseUsed": False,
        "boneCount": len(bones),
        "restFingerprint": character_rest_fingerprint(rig),
    }
    return rig, diagnostics
