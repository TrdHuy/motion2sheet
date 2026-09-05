from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import bpy
from io_scene_fbx import parse_fbx
from mathutils import Matrix, Vector

from motion2sheet.motion.extract.blender import clean_scene, find_armature, import_motion
from motion2sheet.motion.model_render.blender_level1 import export_armature_only_fbx
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


IDENTITY_CARRIER_START = 1
IDENTITY_CARRIER_END = 2


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


def capture_imported_rest_rig_document(
    input_path: Path,
    armature: bpy.types.Object,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Capture the EditBone rest representation produced by the current FBX import.

    This is a static rest snapshot only. It never reads the active Action and never
    samples a scene frame. `capture_character_rig_document` applies the additional
    identity-carrier FBX encoding normalization used by canonical character authority.
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
        "mode": "fbx-imported-edit-rest-v1",
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


def _attach_identity_encoding_carrier(armature: bpy.types.Object) -> bpy.types.Action:
    """Attach a synthetic all-identity Action solely to select FBX animation-stack encoding.

    This Action is not motion authority and contains no source animation sample. Both
    keyed frames are exactly PoseBone.matrix_basis = identity for every bone. Its only
    purpose is to make Blender use the same FBX armature encoding path as motion-only
    assets so local rest representation is clip-independent and comparable at Level 1.
    """

    armature.animation_data_clear()
    action = bpy.data.actions.new("M2S_CANONICAL_REST_IDENTITY_CARRIER")
    armature.animation_data_create().action = action
    scene = bpy.context.scene
    for frame in (IDENTITY_CARRIER_START, IDENTITY_CARRIER_END):
        scene.frame_set(frame)
        for pose_bone in armature.pose.bones:
            pose_bone.rotation_mode = "QUATERNION"
            pose_bone.matrix_basis = Matrix.Identity(4)
            pose_bone.keyframe_insert(data_path="location", frame=frame, group=pose_bone.name)
            pose_bone.keyframe_insert(data_path="rotation_quaternion", frame=frame, group=pose_bone.name)
            pose_bone.keyframe_insert(data_path="scale", frame=frame, group=pose_bone.name)
    for fcurve in action.fcurves:
        for keyframe in fcurve.keyframe_points:
            keyframe.interpolation = "LINEAR"
    scene.frame_set(IDENTITY_CARRIER_START)
    bpy.context.view_layer.update()
    return action


def _export_rest_encoding_fbx(armature: bpy.types.Object, output: Path) -> None:
    """Encode static rest through the same FBX path used by normalized motion.

    The duplicate never receives the source Action. It carries only a fresh synthetic
    identity Action, so no animation pose can define or alter character rest.
    """

    duplicate = armature.copy()
    duplicate_data = armature.data.copy()
    duplicate.data = duplicate_data
    duplicate.name = f"{armature.name}__M2S_CANONICAL_REST"
    duplicate.data.name = f"{armature.data.name}__M2S_CANONICAL_REST"
    bpy.context.collection.objects.link(duplicate)
    carrier = _attach_identity_encoding_carrier(duplicate)
    try:
        # Use exactly the same PR12-local FBX settings/helper as motion normalization.
        # The helper requires an Action; this identity carrier satisfies that encoding
        # requirement without reading or sampling the source clip.
        export_armature_only_fbx(duplicate, output)
    finally:
        duplicate.animation_data_clear()
        bpy.data.objects.remove(duplicate, do_unlink=True)
        if carrier.users == 0:
            bpy.data.actions.remove(carrier)
        if duplicate_data.users == 0:
            bpy.data.armatures.remove(duplicate_data)
        bpy.context.view_layer.update()


def capture_character_rig_document(
    input_path: Path,
    armature: bpy.types.Object,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create the clip-independent canonical character rest rig.

    Authority starts from source FBX bind/edit rest. A duplicate armature receives a
    newly generated all-identity two-frame carrier Action and is FBX round-tripped using
    the same encoding path as motion normalization. The source Action is never read and
    no source animation frame is sampled or copied into rest authority.
    """

    imported_rig, imported_diagnostics = capture_imported_rest_rig_document(input_path, armature)
    original_object_name = armature.name
    original_data_name = armature.data.name

    with tempfile.TemporaryDirectory(prefix="motion2sheet-character-rest-") as temp_dir:
        rest_fbx = Path(temp_dir) / "canonical-rest.fbx"
        _export_rest_encoding_fbx(armature, rest_fbx)
        before_names = {obj.name for obj in bpy.context.scene.objects}
        bpy.ops.import_scene.fbx(filepath=str(rest_fbx))
        imported_objects = [obj for obj in bpy.context.scene.objects if obj.name not in before_names]
        canonical_armatures = [obj for obj in imported_objects if obj.type == "ARMATURE"]
        if len(canonical_armatures) != 1:
            raise RuntimeError(
                "identity-carrier FBX normalization must import exactly one armature; "
                f"found {len(canonical_armatures)}"
            )
        canonical_armature = canonical_armatures[0]
        canonical_data = canonical_armature.data
        canonical_rig, _canonical_import_diagnostics = capture_imported_rest_rig_document(
            input_path,
            canonical_armature,
        )
        # Object/data names are provenance rather than rest semantics; do not expose
        # the private staging names in reusable character authority.
        canonical_rig["armatureObject"]["name"] = original_object_name
        canonical_rig["armatureObject"]["dataName"] = original_data_name
        canonical_rig["id"] = character_rig_id(canonical_rig)
        canonical_rig = validate_rig_document(canonical_rig)

        for obj in imported_objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        if canonical_data.users == 0:
            bpy.data.armatures.remove(canonical_data)
        bpy.context.view_layer.update()

    diagnostics = {
        "mode": "fbx-bind-edit-rest-canonical-v1",
        "restAuthority": "armature-editGeometry",
        "restEncodingNormalization": "identity-carrier armature FBX round-trip",
        "restEncodingCarrier": "synthetic-all-identity-two-frame-action",
        "restEncodingCarrierFrames": [IDENTITY_CARRIER_START, IDENTITY_CARRIER_END],
        "restEncodingCarrierDefinesRest": False,
        "restEncodingSourceAnimationRead": False,
        "restEncodingSourceAnimationSampled": False,
        "restEncodingPoseBasis": "identity",
        "derivedRestCache": "orthogonalized EditBone orientation + head translation",
        "sourceFormatAuthority": "static-fbx-transform-stack-only",
        "animationIndependent": True,
        "animationActionRead": False,
        "animationFrameSampled": False,
        "firstAnimationPoseUsed": False,
        "boneCount": len(canonical_rig["bones"]),
        "importedRestFingerprint": imported_diagnostics["restFingerprint"],
        "restFingerprint": character_rest_fingerprint(canonical_rig),
    }
    return canonical_rig, diagnostics
