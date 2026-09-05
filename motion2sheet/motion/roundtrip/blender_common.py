from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

import bpy
from mathutils import Matrix, Quaternion, Vector

from motion2sheet.motion.extract.blender import activate_animation, clean_scene, find_armature, import_motion

MATRIX_TRS_TOLERANCE = 2e-6
MATRIX_SHEAR_TOLERANCE = 1e-5


def source_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_profile_id(stem: str, suffix: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in stem).strip("-") or "source"
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return f"{cleaned}-{suffix}-v1"


def _clean_float(value: float) -> float:
    value = float(value)
    return 0.0 if abs(value) < 1e-15 else value


def canonical_quaternion(rotation: Quaternion) -> Quaternion:
    result = rotation.copy()
    result.normalize()
    values = (result.w, result.x, result.y, result.z)
    for value in values:
        if abs(value) > 1e-15:
            if value < 0:
                result.negate()
            break
    return result


def canonical_quaternion_values(rotation: Quaternion) -> list[float]:
    values = [float(rotation.w), float(rotation.x), float(rotation.y), float(rotation.z)]
    norm = math.sqrt(sum(value * value for value in values))
    if norm <= 1e-15:
        raise RuntimeError("Cannot serialize a zero-length quaternion")
    values = [value / norm for value in values]
    for value in values:
        if abs(value) > 1e-15:
            if value < 0:
                values = [-component for component in values]
            break
    return [_clean_float(value) for value in values]


def matrix_residual(first: Matrix, second: Matrix) -> float:
    return max(abs(float(first[row][column]) - float(second[row][column])) for row in range(4) for column in range(4))


def matrix_shear_metric(matrix: Matrix) -> float:
    basis = matrix.to_3x3()
    axes = [basis.col[index].copy() for index in range(3)]
    if any(axis.length <= 1e-12 for axis in axes):
        raise RuntimeError("Degenerate transform axis cannot be represented as stable TRS")
    for axis in axes:
        axis.normalize()
    return max(abs(float(axes[i].dot(axes[j]))) for i in range(3) for j in range(i + 1, 3))


def matrix_to_trs(
    matrix: Matrix,
    label: str,
    *,
    tolerance: float = MATRIX_TRS_TOLERANCE,
    shear_tolerance: float = MATRIX_SHEAR_TOLERANCE,
) -> dict[str, list[float]]:
    shear = matrix_shear_metric(matrix)
    if shear > shear_tolerance:
        raise RuntimeError(
            f"{label} contains shear/non-orthogonal basis that TRS cannot preserve; "
            f"normalized-axis dot={shear:.12g} > {shear_tolerance:.12g}. Source transforms fail closed."
        )
    translation, rotation, scale = matrix.decompose()
    rotation = canonical_quaternion(rotation)
    recomposed = Matrix.LocRotScale(translation, rotation, scale)
    residual = matrix_residual(matrix, recomposed)
    if residual > tolerance:
        raise RuntimeError(
            f"{label} is not representable as translation/quaternion/scale within Blender numeric precision; "
            f"matrix residual={residual:.12g} > {tolerance:.12g}; shearMetric={shear:.12g}."
        )
    return {
        "translation": [_clean_float(value) for value in translation],
        "rotationQuaternion": canonical_quaternion_values(rotation),
        "scale": [_clean_float(value) for value in scale],
    }


def trs_to_matrix(data: dict[str, Any]) -> Matrix:
    translation = Vector(data["translation"])
    rotation = Quaternion(data["rotationQuaternion"])
    rotation.normalize()
    scale = Vector(data["scale"])
    return Matrix.LocRotScale(translation, rotation, scale)


def integer_action_range(action: bpy.types.Action) -> tuple[int, int]:
    raw_start, raw_end = (float(value) for value in action.frame_range)
    start = int(round(raw_start))
    end = int(round(raw_end))
    if abs(raw_start - start) > 1e-6 or abs(raw_end - end) > 1e-6:
        raise RuntimeError(
            f"POC v1 requires an integer source action range; got {raw_start:.9f}..{raw_end:.9f}. "
            "Subframe/tangent preservation is outside the v1 contract."
        )
    if end < start:
        raise RuntimeError(f"Invalid action frame range: {raw_start}..{raw_end}")
    return start, end


def scene_fps(scene: bpy.types.Scene) -> tuple[float, int, float]:
    fps_int = int(scene.render.fps)
    fps_base = float(scene.render.fps_base)
    if fps_int <= 0 or fps_base <= 0:
        raise RuntimeError(f"Invalid scene FPS: fps={fps_int}, fpsBase={fps_base}")
    return float(fps_int / fps_base), fps_int, fps_base


def assert_source_supported(armature: bpy.types.Object) -> None:
    if armature.constraints:
        raise RuntimeError("Source armature object constraints are not supported by round-trip POC v1")
    constrained = [pose_bone.name for pose_bone in armature.pose.bones if pose_bone.constraints]
    if constrained:
        raise RuntimeError(
            "Source pose-bone constraints are not supported by round-trip POC v1: " + ", ".join(sorted(constrained))
        )
    if armature.animation_data:
        active_nla = [track.name for track in armature.animation_data.nla_tracks if not track.mute and any(not strip.mute for strip in track.strips)]
        if active_nla:
            raise RuntimeError(
                "Active NLA composition is not supported by round-trip POC v1; source must resolve to one Action: "
                + ", ".join(active_nla)
            )


def bone_depth(bone: bpy.types.Bone) -> int:
    depth = 0
    current = bone.parent
    while current is not None:
        depth += 1
        current = current.parent
    return depth


def ordered_bones(armature: bpy.types.Object) -> list[bpy.types.Bone]:
    return sorted(armature.data.bones, key=lambda bone: (bone_depth(bone), bone.name))


def bone_properties(bone: bpy.types.Bone) -> dict[str, Any]:
    result: dict[str, Any] = {
        "useConnect": bool(bone.use_connect),
        "useDeform": bool(bone.use_deform),
        "useInheritRotation": bool(bone.use_inherit_rotation),
        "useLocalLocation": bool(bone.use_local_location),
        "inheritScale": str(bone.inherit_scale),
        "headRadius": _clean_float(bone.head_radius),
        "tailRadius": _clean_float(bone.tail_radius),
        "envelopeDistance": _clean_float(bone.envelope_distance),
        "envelopeWeight": _clean_float(bone.envelope_weight),
    }
    if hasattr(bone, "use_relative_parent"):
        result["useRelativeParent"] = bool(bone.use_relative_parent)
    return result


def capture_edit_geometry(armature: bpy.types.Object) -> dict[str, dict[str, Any]]:
    bpy.ops.object.mode_set(mode="OBJECT") if armature.mode != "OBJECT" else None
    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        return {
            edit_bone.name: {
                "head": [_clean_float(value) for value in edit_bone.head],
                "tail": [_clean_float(value) for value in edit_bone.tail],
                "roll": _clean_float(edit_bone.roll),
            }
            for edit_bone in armature.data.edit_bones
        }
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")


def capture_rig_document(input_path: Path, armature: bpy.types.Object) -> dict[str, Any]:
    bones: list[dict[str, Any]] = []
    for bone in ordered_bones(armature):
        local_matrix = bone.matrix_local.copy()
        if bone.parent is not None:
            local_matrix = bone.parent.matrix_local.inverted_safe() @ local_matrix
        bones.append(
            {
                "name": bone.name,
                "parent": bone.parent.name if bone.parent else None,
                "rest": matrix_to_trs(local_matrix, f"rest transform for bone {bone.name}"),
                "length": _clean_float(bone.length),
                "properties": bone_properties(bone),
            }
        )
    edit_geometry = capture_edit_geometry(armature)
    for bone in bones:
        bone["editGeometry"] = edit_geometry[bone["name"]]
    scene = bpy.context.scene
    sha = source_sha256(input_path)
    return {
        "schema": "motion2sheet.source-rig",
        "version": 1,
        "id": stable_profile_id(input_path.stem, "rig"),
        "source": {
            "format": input_path.suffix.lstrip(".").upper(),
            "filename": input_path.name,
            "sha256": sha,
            "importer": "blender-fbx" if input_path.suffix.lower() == ".fbx" else "blender-bvh",
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
            "metersPerBlenderUnit": _clean_float(scene.unit_settings.scale_length or 1.0),
        },
        "restAuthority": "editGeometry",
        "editGeometrySpace": "armature-local",
        "armatureObject": {
            "name": armature.name,
            "dataName": armature.data.name,
            "transform": matrix_to_trs(armature.matrix_world.copy(), "armature object transform"),
        },
        "bones": bones,
    }


def capture_animation_document(input_path: Path, armature: bpy.types.Object, action: bpy.types.Action, rig: dict[str, Any]) -> dict[str, Any]:
    assert_source_supported(armature)
    scene = bpy.context.scene
    start, end = integer_action_range(action)
    fps, fps_int, fps_base = scene_fps(scene)
    bone_names = [bone["name"] for bone in rig["bones"]]
    frames: list[dict[str, Any]] = []
    for frame in range(start, end + 1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        transforms: dict[str, Any] = {}
        for bone_name in bone_names:
            pose_bone = armature.pose.bones[bone_name]
            transforms[bone_name] = matrix_to_trs(
                pose_bone.matrix_basis.copy(),
                f"pose basis transform for bone {bone_name} at frame {frame}",
            )
        frames.append({"frame": frame, "bones": transforms})
    return {
        "schema": "motion2sheet.source-animation",
        "version": 1,
        "id": stable_profile_id(f"{input_path.stem}-{action.name}", "animation"),
        "rig": {"id": rig["id"]},
        "source": {
            "format": input_path.suffix.lstrip(".").upper(),
            "filename": input_path.name,
            "sha256": rig["source"]["sha256"],
            "action": action.name,
        },
        "fps": _clean_float(fps),
        "fpsNumerator": fps_int,
        "fpsBase": _clean_float(fps_base),
        "frameRange": [start, end],
        "frameCount": end - start + 1,
        "sampling": {
            "policy": "all-integer-source-frames-inclusive",
            "step": 1,
            "continuousSubframeBehaviorPreserved": False,
        },
        "transformSpace": {
            "name": "blender-pose-matrix-basis",
            "description": "Per-bone PoseBone.matrix_basis: pose-local delta relative to the bone rest basis, serialized as TRS.",
        },
        "frames": frames,
    }


def import_source(input_path: Path) -> tuple[bpy.types.Object, bpy.types.Action]:
    clean_scene()
    if input_path.suffix.lower() == ".bvh":
        # Source Animation timing must use the BVH-declared Frame Time rather than
        # the caller's pre-existing scene FPS. Keep this timing-aware import local
        # to the round-trip authority boundary so generic motion extraction keeps
        # its historical behavior.
        bpy.ops.import_anim.bvh(filepath=str(input_path), target="ARMATURE", update_scene_fps=True)
    else:
        import_motion(input_path)
    armature = find_armature()
    action = activate_animation(armature)
    bpy.context.view_layer.update()
    return armature, action


def world_pose_snapshot(armature: bpy.types.Object, frame: int) -> dict[str, dict[str, list[float]]]:
    scene = bpy.context.scene
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    evaluated = armature.evaluated_get(bpy.context.evaluated_depsgraph_get())
    result: dict[str, dict[str, list[float]]] = {}
    for pose_bone in sorted(evaluated.pose.bones, key=lambda bone: bone.name):
        world_matrix = evaluated.matrix_world @ pose_bone.matrix
        head = evaluated.matrix_world @ pose_bone.head
        tail = evaluated.matrix_world @ pose_bone.tail
        result[pose_bone.name] = {
            "matrix": [_clean_float(world_matrix[row][column]) for row in range(4) for column in range(4)],
            "head": [_clean_float(value) for value in head],
            "tail": [_clean_float(value) for value in tail],
        }
    return result


def local_pose_snapshot(armature: bpy.types.Object, frame: int) -> dict[str, dict[str, list[float]]]:
    scene = bpy.context.scene
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    return {
        pose_bone.name: matrix_to_trs(pose_bone.matrix_basis.copy(), f"snapshot {pose_bone.name} frame {frame}")
        for pose_bone in sorted(armature.pose.bones, key=lambda bone: bone.name)
    }
