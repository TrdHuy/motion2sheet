from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import bpy

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from motion2sheet.motion.extract.blender import activate_animation, clean_scene, find_armature, import_motion
from motion2sheet.motion.roundtrip.blender_common import (
    integer_action_range,
    local_pose_snapshot,
    matrix_to_trs,
    ordered_bones,
    scene_fps,
    world_pose_snapshot,
)
from motion2sheet.motion.roundtrip.schema import read_json, validate_animation_document, validate_rig_document

TRANSLATION_TOLERANCE = 1e-5
ANGULAR_TOLERANCE_DEG = 1e-4
SCALE_TOLERANCE = 1e-6
REST_TOLERANCE = 1e-5
WORLD_TOLERANCE = 1e-5


def _argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def _vec_error(first: list[float], second: list[float]) -> float:
    return math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(first, second)))


def _scale_error(first: list[float], second: list[float]) -> float:
    return max(abs(float(a) - float(b)) for a, b in zip(first, second))


def _normalized_quaternion(values: list[float]) -> list[float]:
    result = [float(value) for value in values]
    norm = math.sqrt(sum(value * value for value in result))
    if norm <= 1e-15:
        raise RuntimeError("Cannot compare a zero-length quaternion")
    return [value / norm for value in result]


def _angular_error(first: list[float], second: list[float]) -> float:
    # Do this in Python double precision. mathutils.Quaternion stores float32;
    # its dot quantization alone can report about 0.03956 degrees for two
    # effectively identical rotations, which is larger than the POC gate.
    q1 = _normalized_quaternion(first)
    q2 = _normalized_quaternion(second)
    dot = abs(sum(a * b for a, b in zip(q1, q2)))
    dot = max(-1.0, min(1.0, dot))
    return math.degrees(2.0 * math.acos(dot))


def capture_structure(armature) -> dict[str, Any]:
    rest: dict[str, Any] = {}
    for bone in ordered_bones(armature):
        matrix = bone.matrix_local.copy()
        if bone.parent:
            matrix = bone.parent.matrix_local.inverted_safe() @ matrix
        rest[bone.name] = {
            "parent": bone.parent.name if bone.parent else None,
            "length": float(bone.length),
            "rest": matrix_to_trs(matrix, f"verification rest {bone.name}"),
        }
    return {
        "boneNames": sorted(rest),
        "parents": {name: rest[name]["parent"] for name in sorted(rest)},
        "lengths": {name: rest[name]["length"] for name in sorted(rest)},
        "rest": {name: rest[name]["rest"] for name in sorted(rest)},
        "armatureObjectTransform": matrix_to_trs(armature.matrix_world.copy(), "verification armature object"),
    }


def capture_scene_state(armature, action, frames: list[int]) -> dict[str, Any]:
    fps, fps_numerator, fps_base = scene_fps(bpy.context.scene)
    action_start, action_end = integer_action_range(action)
    return {
        "structure": capture_structure(armature),
        "fps": fps,
        "fpsNumerator": fps_numerator,
        "fpsBase": fps_base,
        "frameRange": [action_start, action_end],
        "local": {str(frame): local_pose_snapshot(armature, frame) for frame in frames},
        "world": {str(frame): world_pose_snapshot(armature, frame) for frame in frames},
    }


def load_source(path: Path, frames: list[int]):
    clean_scene()
    import_motion(path)
    armature = find_armature()
    action = activate_animation(armature)
    return capture_scene_state(armature, action, frames)


def load_blend(path: Path, frames: list[int]):
    bpy.ops.wm.open_mainfile(filepath=str(path))
    armature = find_armature()
    action = activate_animation(armature)
    return capture_scene_state(armature, action, frames)


def compare_structure(source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    source_structure = source["structure"]
    target_structure = target["structure"]
    names_exact = source_structure["boneNames"] == target_structure["boneNames"]
    parents_exact = source_structure["parents"] == target_structure["parents"]
    fps_error = abs(float(source["fps"]) - float(target["fps"]))
    range_exact = source["frameRange"] == target["frameRange"]
    max_length_error = 0.0
    max_rest_translation = 0.0
    max_rest_angle = 0.0
    max_rest_scale = 0.0
    worst_bone = None
    common = sorted(set(source_structure["boneNames"]) & set(target_structure["boneNames"]))
    for name in common:
        length_error = abs(source_structure["lengths"][name] - target_structure["lengths"][name])
        source_rest = source_structure["rest"][name]
        target_rest = target_structure["rest"][name]
        translation_error = _vec_error(source_rest["translation"], target_rest["translation"])
        angular_error = _angular_error(source_rest["rotationQuaternion"], target_rest["rotationQuaternion"])
        scale_error = _scale_error(source_rest["scale"], target_rest["scale"])
        score = max(length_error, translation_error, angular_error, scale_error)
        if score >= max(max_length_error, max_rest_translation, max_rest_angle, max_rest_scale):
            worst_bone = name
        max_length_error = max(max_length_error, length_error)
        max_rest_translation = max(max_rest_translation, translation_error)
        max_rest_angle = max(max_rest_angle, angular_error)
        max_rest_scale = max(max_rest_scale, scale_error)
    source_object = source_structure["armatureObjectTransform"]
    target_object = target_structure["armatureObjectTransform"]
    object_translation = _vec_error(source_object["translation"], target_object["translation"])
    object_angle = _angular_error(source_object["rotationQuaternion"], target_object["rotationQuaternion"])
    object_scale = _scale_error(source_object["scale"], target_object["scale"])
    passed = (
        names_exact and parents_exact and range_exact and fps_error <= 1e-9
        and max_length_error <= REST_TOLERANCE
        and max_rest_translation <= REST_TOLERANCE
        and max_rest_angle <= ANGULAR_TOLERANCE_DEG
        and max_rest_scale <= SCALE_TOLERANCE
        and object_translation <= REST_TOLERANCE
        and object_angle <= ANGULAR_TOLERANCE_DEG
        and object_scale <= SCALE_TOLERANCE
    )
    return {
        "pass": passed,
        "boneCountSource": len(source_structure["boneNames"]),
        "boneCountTarget": len(target_structure["boneNames"]),
        "boneNamesExact": names_exact,
        "parentHierarchyExact": parents_exact,
        "frameRangeExact": range_exact,
        "fpsError": fps_error,
        "maxBoneLengthError": max_length_error,
        "maxRestTranslationError": max_rest_translation,
        "maxRestAngularErrorDeg": max_rest_angle,
        "maxRestScaleError": max_rest_scale,
        "armatureTranslationError": object_translation,
        "armatureAngularErrorDeg": object_angle,
        "armatureScaleError": object_scale,
        "worstBone": worst_bone,
    }


def compare_local(source: dict[str, Any], target: dict[str, Any], frames: list[int]) -> dict[str, Any]:
    max_translation = 0.0
    max_angle = 0.0
    max_scale = 0.0
    translation_at = {"frame": None, "bone": None}
    angular_at = {"frame": None, "bone": None}
    scale_at = {"frame": None, "bone": None}
    for frame in frames:
        source_bones = source["local"][str(frame)]
        target_bones = target["local"][str(frame)]
        if set(source_bones) != set(target_bones):
            return {"pass": False, "reason": f"bone set mismatch at frame {frame}"}
        for bone_name in source_bones:
            first = source_bones[bone_name]
            second = target_bones[bone_name]
            translation = _vec_error(first["translation"], second["translation"])
            angle = _angular_error(first["rotationQuaternion"], second["rotationQuaternion"])
            scale = _scale_error(first["scale"], second["scale"])
            if translation > max_translation:
                max_translation = translation
                translation_at = {"frame": frame, "bone": bone_name}
            if angle > max_angle:
                max_angle = angle
                angular_at = {"frame": frame, "bone": bone_name}
            if scale > max_scale:
                max_scale = scale
                scale_at = {"frame": frame, "bone": bone_name}

    normalized = (
        ("translation", max_translation / TRANSLATION_TOLERANCE, translation_at),
        ("rotation", max_angle / ANGULAR_TOLERANCE_DEG, angular_at),
        ("scale", max_scale / SCALE_TOLERANCE, scale_at),
    )
    worst_kind, _worst_ratio, worst_at = max(normalized, key=lambda item: item[1])
    return {
        "pass": max_translation <= TRANSLATION_TOLERANCE and max_angle <= ANGULAR_TOLERANCE_DEG and max_scale <= SCALE_TOLERANCE,
        "maxTranslationError": max_translation,
        "maxAngularErrorDeg": max_angle,
        "maxScaleError": max_scale,
        "maxTranslationAt": translation_at,
        "maxAngularAt": angular_at,
        "maxScaleAt": scale_at,
        "worstFrame": worst_at["frame"],
        "worstBone": worst_at["bone"],
        "worstKind": worst_kind,
    }


def compare_world(source: dict[str, Any], target: dict[str, Any], frames: list[int]) -> dict[str, Any]:
    max_matrix = 0.0
    max_head = 0.0
    max_tail = 0.0
    worst_frame = None
    worst_bone = None
    worst_kind = None
    for frame in frames:
        source_bones = source["world"][str(frame)]
        target_bones = target["world"][str(frame)]
        if set(source_bones) != set(target_bones):
            return {"pass": False, "reason": f"bone set mismatch at frame {frame}"}
        for bone_name in source_bones:
            first = source_bones[bone_name]
            second = target_bones[bone_name]
            matrix_error = max(abs(a - b) for a, b in zip(first["matrix"], second["matrix"]))
            head_error = _vec_error(first["head"], second["head"])
            tail_error = _vec_error(first["tail"], second["tail"])
            local_best = max(matrix_error, head_error, tail_error)
            if local_best > max(max_matrix, max_head, max_tail):
                worst_frame = frame
                worst_bone = bone_name
                worst_kind = "matrix" if matrix_error == local_best else ("head" if head_error == local_best else "tail")
            max_matrix = max(max_matrix, matrix_error)
            max_head = max(max_head, head_error)
            max_tail = max(max_tail, tail_error)
    return {
        "pass": max_matrix <= WORLD_TOLERANCE and max_head <= WORLD_TOLERANCE and max_tail <= WORLD_TOLERANCE,
        "maxMatrixError": max_matrix,
        "maxHeadError": max_head,
        "maxTailError": max_tail,
        "maxWorldError": max(max_matrix, max_head, max_tail),
        "worstFrame": worst_frame,
        "worstBone": worst_bone,
        "worstKind": worst_kind,
    }


def json_authority_state(rig: dict[str, Any], animation: dict[str, Any]) -> dict[str, Any]:
    return {
        "structure": {
            "boneNames": sorted(bone["name"] for bone in rig["bones"]),
            "parents": {bone["name"]: bone["parent"] for bone in rig["bones"]},
            "lengths": {bone["name"]: float(bone["length"]) for bone in rig["bones"]},
            "rest": {bone["name"]: bone["rest"] for bone in rig["bones"]},
            "armatureObjectTransform": rig["armatureObject"]["transform"],
        },
        "fps": float(animation["fps"]),
        "fpsNumerator": animation["fpsNumerator"],
        "fpsBase": animation["fpsBase"],
        "frameRange": animation["frameRange"],
        "local": {str(entry["frame"]): entry["bones"] for entry in animation["frames"]},
    }


def _aggregate_local_metric(
    candidates: list[tuple[str, dict[str, Any]]],
    value_key: str,
    at_key: str,
) -> dict[str, Any]:
    stage, metrics = max(candidates, key=lambda item: item[1].get(value_key, float("inf")))
    at = metrics.get(at_key, {})
    return {
        "stage": stage,
        "frame": at.get("frame"),
        "bone": at.get("bone"),
        "error": metrics.get(value_key),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--rig", required=True)
    parser.add_argument("--animation", required=True)
    parser.add_argument("--blend", required=True)
    parser.add_argument("--fbx", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(_argv())
    rig = validate_rig_document(read_json(Path(args.rig)))
    animation = validate_animation_document(read_json(Path(args.animation)), rig)
    frames = list(range(animation["frameRange"][0], animation["frameRange"][1] + 1))
    source = load_source(Path(args.source).resolve(), frames)
    json_state = json_authority_state(rig, animation)
    source_json_structure = compare_structure(source, json_state)
    source_json_local = compare_local(source, json_state, frames)

    reconstructed_blend = load_blend(Path(args.blend).resolve(), frames)
    blend_structure = compare_structure(source, reconstructed_blend)
    blend_local = compare_local(source, reconstructed_blend, frames)
    blend_world = compare_world(source, reconstructed_blend, frames)

    reimported_fbx = load_source(Path(args.fbx).resolve(), frames)
    fbx_structure = compare_structure(source, reimported_fbx)
    fbx_local = compare_local(source, reimported_fbx, frames)
    fbx_world = compare_world(source, reimported_fbx, frames)

    aggregate_structure = blend_structure["pass"] and fbx_structure["pass"] and source_json_structure["pass"]
    local_candidates = [("sourceJson", source_json_local), ("reconstructedBlend", blend_local), ("reimportedFbx", fbx_local)]
    worst_local_stage, worst_local = max(
        local_candidates,
        key=lambda item: max(
            item[1].get("maxTranslationError", float("inf")) / TRANSLATION_TOLERANCE,
            item[1].get("maxAngularErrorDeg", float("inf")) / ANGULAR_TOLERANCE_DEG,
            item[1].get("maxScaleError", float("inf")) / SCALE_TOLERANCE,
        ),
    )
    translation_worst = _aggregate_local_metric(local_candidates, "maxTranslationError", "maxTranslationAt")
    angular_worst = _aggregate_local_metric(local_candidates, "maxAngularErrorDeg", "maxAngularAt")
    scale_worst = _aggregate_local_metric(local_candidates, "maxScaleError", "maxScaleAt")
    world_candidates = [("reconstructedBlend", blend_world), ("reimportedFbx", fbx_world)]
    worst_world_stage, worst_world = max(world_candidates, key=lambda item: item[1].get("maxWorldError", float("inf")))
    result = {
        "schema": "motion2sheet.roundtrip-verification",
        "version": 1,
        "pass": aggregate_structure and all(item[1]["pass"] for item in local_candidates) and all(item[1]["pass"] for item in world_candidates),
        "tolerances": {
            "translation": TRANSLATION_TOLERANCE,
            "angularDeg": ANGULAR_TOLERANCE_DEG,
            "scale": SCALE_TOLERANCE,
            "rest": REST_TOLERANCE,
            "world": WORLD_TOLERANCE,
        },
        "structure": {
            "pass": aggregate_structure,
            "sourceJson": source_json_structure,
            "reconstructedBlend": blend_structure,
            "reimportedFbx": fbx_structure,
        },
        "localTransform": {
            "pass": all(item[1]["pass"] for item in local_candidates),
            "maxTranslationError": translation_worst["error"],
            "maxAngularErrorDeg": angular_worst["error"],
            "maxScaleError": scale_worst["error"],
            "maxTranslationAt": translation_worst,
            "maxAngularAt": angular_worst,
            "maxScaleAt": scale_worst,
            "worstStage": worst_local_stage,
            "worstFrame": worst_local.get("worstFrame"),
            "worstBone": worst_local.get("worstBone"),
            "worstKind": worst_local.get("worstKind"),
            "stages": {name: metrics for name, metrics in local_candidates},
        },
        "worldPose": {
            "pass": all(item[1]["pass"] for item in world_candidates),
            "maxWorldError": max(item[1].get("maxWorldError", float("inf")) for item in world_candidates),
            "maxHeadError": max(item[1].get("maxHeadError", float("inf")) for item in world_candidates),
            "maxTailError": max(item[1].get("maxTailError", float("inf")) for item in world_candidates),
            "maxMatrixError": max(item[1].get("maxMatrixError", float("inf")) for item in world_candidates),
            "worstStage": worst_world_stage,
            "worstFrame": worst_world.get("worstFrame"),
            "worstBone": worst_world.get("worstBone"),
            "worstKind": worst_world.get("worstKind"),
            "stages": {name: metrics for name, metrics in world_candidates},
        },
        "jsonOnlyReconstruction": {"pass": blend_structure["pass"] and blend_local["pass"] and blend_world["pass"]},
        "fbxReimport": {"pass": fbx_structure["pass"] and fbx_local["pass"] and fbx_world["pass"]},
    }
    visual_pose = {
        "frameRange": animation["frameRange"],
        "source": source["world"],
        "reconstructed": reimported_fbx["world"],
    }
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "verification.numeric.json").write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    visual_dir = output / "visual"
    visual_dir.mkdir(parents=True, exist_ok=True)
    (visual_dir / "pose_data.json").write_text(json.dumps(visual_pose, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"pass": result["pass"], "local": result["localTransform"], "world": result["worldPose"]}, indent=2))
    if not result["pass"]:
        raise RuntimeError("Round-trip numerical verification failed; see verification.numeric.json")


if __name__ == "__main__":
    main()