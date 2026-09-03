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
    canonical_quaternion_values,
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
    """Capture Blender EditBone authority without consulting pose/action state."""

    if armature.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        result: dict[str, dict[str, Any]] = {}
        for edit_bone in armature.data.edit_bones:
            # EditBone.matrix can carry tiny floating-point non-orthogonality after
            # FBX import. editGeometry remains the sole rest authority. Normalize
            # only the derived orientation cache through a unit quaternion rather
            # than loosening PR #11 matrix/TRS tolerances.
            orientation = edit_bone.matrix.to_quaternion()
            orientation.normalize()
            result[edit_bone.name] = {
                "head": [float(value) for value in edit_bone.head],
                "tail": [float(value) for value in edit_bone.tail],
                "roll": float(edit_bone.roll),
                "orientation": orientation.copy(),
            }
        return result
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")


def _derived_rest_cache(name: str, parent: str | None, edit: dict[str, dict[str, Any]]) -> dict[str, list[float]]:
    row = edit[name]
    child_rotation = row["orientation"].copy()
    child_rotation.normalize()
    child_head = Vector(row["head"])
    if parent is None:
        translation = child_head
        local_rotation = child_rotation
    else:
        parent_row = edit[parent]
        parent_rotation = parent_row["orientation"].copy()
        parent_rotation.normalize()
        inverse_parent = parent_rotation.inverted()
        translation = inverse_parent @ (child_head - Vector(parent_row["head"]))
        local_rotation = inverse_parent @ child_rotation
        local_rotation.normalize()
    return {
        "translation": [float(value) for value in translation],
        "rotationQuaternion": canonical_quaternion_values(local_rotation),
        "scale": [1.0, 1.0, 1.0],
    }


def capture_character_rig_document(input_path: Path, armature: bpy.types.Object) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create a clip-independent character rig from FBX edit/rest data.

    `editGeometry` is the sole rest authority. The `rest` TRS fields are derived
    inspection caches reconstructed from orthogonalized EditBone orientation and
    head positions; no animation action or frame is consulted.
    """

    edit = _capture_edit_rest(armature)
    bones: list[dict[str, Any]] = []
    for bone in ordered_bones(armature):
        row = edit[bone.name]
        head = Vector(row["head"])
        tail = Vector(row["tail"])
        parent = bone.parent.name if bone.parent else None
        bones.append(
            {
                "name": bone.name,
                "parent": parent,
                "rest": _derived_rest_cache(bone.name, parent, edit),
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
        "derivedRestCache": "orthogonalized EditBone orientation + head translation",
        "sourceFormatAuthority": "static-fbx-transform-stack-only",
        "animationIndependent": True,
        "animationActionRead": False,
        "animationFrameSampled": False,
        "firstAnimationPoseUsed": False,
        "boneCount": len(bones),
        "restFingerprint": character_rest_fingerprint(rig),
    }
    return rig, diagnostics
