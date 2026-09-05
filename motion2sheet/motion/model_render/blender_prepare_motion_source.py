from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

import bpy
from mathutils import Matrix

from motion2sheet.motion.model_render.blender_level1 import export_action_with_static_rest_fbx
from motion2sheet.motion.model_render.blender_rest_authority import (
    capture_character_rig_document,
    capture_imported_rest_rig_document,
)
from motion2sheet.motion.roundtrip.blender_common import (
    capture_rig_document,
    import_source,
    integer_action_range,
    ordered_bones,
    scene_fps,
)
from motion2sheet.motion.roundtrip.blender_json_scene import build_armature, clean_scene
from motion2sheet.motion.roundtrip.fbx import extract_fbx_metadata_and_diagnostics
from motion2sheet.motion.roundtrip.schema import validate_rig_document
from motion2sheet.motion.skin import validate_level1_rig_compatibility

# Canonical rebase itself stays at the original strict 10-micrometer world-space
# envelope. A separate, explicitly reported envelope accounts only for FBX float
# serialization/import accumulation on longer clips. Neither value affects the
# Level-1 rest-basis gate, which remains 0.001 degrees in skin.compatibility.
CANONICAL_REBASE_TRANSLATION_TOLERANCE = 1e-5
CANONICAL_REBASE_HEAD_TAIL_TOLERANCE = 1e-5
FBX_SERIALIZATION_TRANSLATION_TOLERANCE = 2e-5
FBX_SERIALIZATION_HEAD_TAIL_TOLERANCE = 2e-5
ROTATION_TOLERANCE_DEGREES = 1e-4
SCALE_TOLERANCE = 1e-6


def _argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _capture_pose(armature, start: int, end: int) -> dict[int, dict[str, dict[str, object]]]:
    result: dict[int, dict[str, dict[str, object]]] = {}
    scene = bpy.context.scene
    for frame in range(start, end + 1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        rows: dict[str, dict[str, object]] = {}
        for bone in armature.pose.bones:
            world = armature.matrix_world @ bone.matrix
            location, rotation, scale = world.decompose()
            head = armature.matrix_world @ bone.head
            tail = armature.matrix_world @ bone.tail
            rows[bone.name] = {
                "matrixArmature": bone.matrix.copy(),
                "location": location.copy(),
                "rotation": rotation.normalized().copy(),
                "scale": scale.copy(),
                "head": head.copy(),
                "tail": tail.copy(),
            }
        result[frame] = rows
    return result


def _compare(
    reference,
    actual,
    parents,
    source_start: int,
    source_end: int,
    frame_offset: int,
    *,
    translation_tolerance: float,
    head_tail_tolerance: float,
    phase: str,
) -> dict[str, object]:
    max_translation = max_head_tail = max_rotation = max_scale = 0.0
    worst_translation = worst_head_tail = worst_rotation = worst_scale = None
    for source_frame in range(source_start, source_end + 1):
        normalized_frame = source_frame + frame_offset
        expected_rows = reference[source_frame]
        actual_rows = actual[normalized_frame]
        if set(expected_rows) != set(actual_rows):
            raise RuntimeError(
                f"normalized motion bone set mismatch at source frame {source_frame} / normalized frame {normalized_frame}: "
                f"missing={sorted(set(expected_rows)-set(actual_rows))} extra={sorted(set(actual_rows)-set(expected_rows))}"
            )
        for name in sorted(expected_rows):
            first = expected_rows[name]
            second = actual_rows[name]
            translation = (first["location"] - second["location"]).length
            head = (first["head"] - second["head"]).length
            tail = (first["tail"] - second["tail"]).length
            head_tail = max(head, tail)
            rotation = math.degrees(first["rotation"].rotation_difference(second["rotation"]).angle)
            scale = max(abs(float(first["scale"][axis]) - float(second["scale"][axis])) for axis in range(3))
            location = {"sourceFrame": source_frame, "normalizedFrame": normalized_frame, "bone": name}
            if translation > max_translation:
                max_translation, worst_translation = translation, location
            if head_tail > max_head_tail:
                max_head_tail, worst_head_tail = head_tail, {**location, "headError": head, "tailError": tail}
            if rotation > max_rotation:
                max_rotation, worst_rotation = rotation, location
            if scale > max_scale:
                max_scale, worst_scale = scale, location
    passed = (
        max_translation <= translation_tolerance
        and max_head_tail <= head_tail_tolerance
        and max_rotation <= ROTATION_TOLERANCE_DEGREES
        and max_scale <= SCALE_TOLERANCE
    )
    return {
        "pass": passed,
        "phase": phase,
        "boneCount": len(parents),
        "exactBoneNames": True,
        "exactHierarchy": True,
        "sourceFrameRange": [source_start, source_end],
        "normalizedFrameRange": [source_start + frame_offset, source_end + frame_offset],
        "frameOffset": frame_offset,
        "frameCount": source_end - source_start + 1,
        "maxWorldTranslationError": max_translation,
        "translationTolerance": translation_tolerance,
        "worstWorldTranslation": worst_translation,
        "maxHeadTailError": max_head_tail,
        "headTailTolerance": head_tail_tolerance,
        "worstHeadTail": worst_head_tail,
        "maxWorldRotationErrorDegrees": max_rotation,
        "rotationToleranceDegrees": ROTATION_TOLERANCE_DEGREES,
        "worstWorldRotation": worst_rotation,
        "maxWorldScaleError": max_scale,
        "scaleTolerance": SCALE_TOLERANCE,
        "worstWorldScale": worst_scale,
    }


def _build_canonical_rebased_action(
    canonical_rig: dict,
    reference: dict[int, dict[str, dict[str, object]]],
    start: int,
    end: int,
    fps_numerator: int,
    fps_base: float,
) -> tuple[bpy.types.Object, bpy.types.Action]:
    """Solve source pose matrices as local motion relative to canonical static rest.

    This is a representation rebase on the exact same bone names/hierarchy, not a
    retarget. The desired per-frame armature-space pose matrices come directly from
    the source animation. Blender solves each PoseBone.matrix_basis against the clean
    canonical EditBone rest; no animation sample is ever promoted to rest authority.
    """

    clean_scene()
    # Source/temporary Actions can outlive deleted objects. Remove them before making
    # the clean motion carrier so the FBX all-actions path can only see this one Action.
    for existing_action in list(bpy.data.actions):
        bpy.data.actions.remove(existing_action)

    armature = build_armature(canonical_rig)
    scene = bpy.context.scene
    scene.render.fps = int(fps_numerator)
    scene.render.fps_base = float(fps_base)
    scene.frame_start = start
    scene.frame_end = end
    action = bpy.data.actions.new("M2S_CANONICAL_REST_REBASED_MOTION")
    armature.animation_data_create().action = action
    bones = ordered_bones(armature)
    expected_names = set(reference[start])
    actual_names = {bone.name for bone in bones}
    if actual_names != expected_names:
        raise RuntimeError(
            "canonical rebase bone set mismatch: "
            f"missing={sorted(expected_names-actual_names)} extra={sorted(actual_names-expected_names)}"
        )
    for pose_bone in armature.pose.bones:
        pose_bone.rotation_mode = "QUATERNION"

    for frame in range(start, end + 1):
        scene.frame_set(frame)
        for pose_bone in armature.pose.bones:
            pose_bone.matrix_basis = Matrix.Identity(4)
        bpy.context.view_layer.update()

        # Parent-before-child assignment lets Blender solve each matrix_basis against
        # the already established parent pose and the canonical rest hierarchy.
        for bone in bones:
            pose_bone = armature.pose.bones[bone.name]
            pose_bone.matrix = reference[frame][bone.name]["matrixArmature"].copy()
            bpy.context.view_layer.update()

        # Key only the solved local basis. The source armature/action is already gone;
        # subsequent playback is canonical rest + these rest-relative local deltas.
        for bone in bones:
            pose_bone = armature.pose.bones[bone.name]
            pose_bone.keyframe_insert(data_path="location", frame=frame, group=bone.name)
            pose_bone.keyframe_insert(data_path="rotation_quaternion", frame=frame, group=bone.name)
            pose_bone.keyframe_insert(data_path="scale", frame=frame, group=bone.name)

    for fcurve in action.fcurves:
        for keyframe in fcurve.keyframe_points:
            keyframe.interpolation = "LINEAR"
    scene.frame_set(start)
    bpy.context.view_layer.update()
    return armature, action


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args(_argv())
    source = Path(args.input).resolve()
    output = Path(args.output).resolve()
    report_path = Path(args.report).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    source_armature, source_action = import_source(source)
    source_start, source_end = integer_action_range(source_action)
    source_frame_count = source_end - source_start + 1
    fps, fps_numerator, fps_base = scene_fps(bpy.context.scene)
    parents = {bone.name: bone.parent.name if bone.parent else None for bone in source_armature.data.bones}

    # Static character authority and motion authority are captured independently.
    # Character rest reads only bind/EditBone/static-FBX data. Source pose matrices
    # below are motion samples only and are never used to derive canonical rest.
    _imported_rig, imported_rest = capture_imported_rest_rig_document(source, source_armature)
    reference = _capture_pose(source_armature, source_start, source_end)
    canonical_source_rig, canonical_rest = capture_character_rig_document(source, source_armature)

    rebased_armature, rebased_action = _build_canonical_rebased_action(
        canonical_source_rig,
        reference,
        source_start,
        source_end,
        fps_numerator,
        fps_base,
    )
    rebased_parents = {bone.name: bone.parent.name if bone.parent else None for bone in rebased_armature.data.bones}
    if rebased_parents != parents:
        raise RuntimeError("canonical motion rebase changed hierarchy")
    rebased_pose = _capture_pose(rebased_armature, source_start, source_end)
    pre_fbx_fidelity = _compare(
        reference,
        rebased_pose,
        parents,
        source_start,
        source_end,
        0,
        translation_tolerance=CANONICAL_REBASE_TRANSLATION_TOLERANCE,
        head_tail_tolerance=CANONICAL_REBASE_HEAD_TAIL_TOLERANCE,
        phase="canonical-rest-rebase-before-fbx",
    )
    if not pre_fbx_fidelity["pass"]:
        raise RuntimeError(f"canonical-rest motion rebase fidelity failed before FBX export: {pre_fbx_fidelity}")

    # Critical separation: static FBX transforms are sampled with no active Action and
    # identity pose basis, while the sole stored Action is baked as the animation stack.
    # This prevents the first motion pose from being folded back into imported rest.
    export_action_with_static_rest_fbx(rebased_armature, rebased_action, output)

    normalized_armature, normalized_action = import_source(output)
    normalized_start, normalized_end = integer_action_range(normalized_action)
    normalized_frame_count = normalized_end - normalized_start + 1
    if normalized_frame_count != source_frame_count:
        raise RuntimeError(
            "normalized motion sample count changed: "
            f"sourceRange={[source_start, source_end]} normalizedRange={[normalized_start, normalized_end]}"
        )
    frame_offset = normalized_start - source_start
    if normalized_end - source_end != frame_offset:
        raise RuntimeError(
            "normalized motion frame numbering is not a constant offset: "
            f"sourceRange={[source_start, source_end]} normalizedRange={[normalized_start, normalized_end]}"
        )
    normalized_parents = {bone.name: bone.parent.name if bone.parent else None for bone in normalized_armature.data.bones}
    if normalized_parents != parents:
        raise RuntimeError("normalized motion hierarchy changed")
    normalized_pose = _capture_pose(normalized_armature, normalized_start, normalized_end)
    post_fbx_fidelity = _compare(
        reference,
        normalized_pose,
        parents,
        source_start,
        source_end,
        frame_offset,
        translation_tolerance=FBX_SERIALIZATION_TRANSLATION_TOLERANCE,
        head_tail_tolerance=FBX_SERIALIZATION_HEAD_TAIL_TOLERANCE,
        phase="after-fbx-serialization-and-import",
    )
    if not post_fbx_fidelity["pass"]:
        raise RuntimeError(f"canonical-rest motion rebase fidelity failed after FBX export: {post_fbx_fidelity}")

    # Reproduce locked PR #11 rig-validation ordering on the generated motion-only FBX.
    normalized_rig = capture_rig_document(output, normalized_armature)
    normalized_bones = [bone["name"] for bone in normalized_rig["bones"]]
    rig_fbx, _animation_fbx, _diagnostic_curves = extract_fbx_metadata_and_diagnostics(
        output,
        normalized_bones,
        normalized_frame_count,
    )
    normalized_rig["sourceFormat"] = {"fbx": rig_fbx}
    normalized_rig = validate_rig_document(normalized_rig)
    if len(normalized_rig["bones"]) != len(parents):
        raise RuntimeError("locked Motion JSON Source Rig capture changed the normalized bone count")

    # Strict existing Level-1 validation is the acceptance gate. No tolerance changes,
    # mappings, retarget solver, or first-pose substitution are permitted here.
    rest_compatibility = validate_level1_rig_compatibility(normalized_rig, canonical_source_rig)

    report = {
        "schema": "motion2sheet.diagnostics.level1-motion-source-normalization",
        "version": 1,
        "reason": "Source pose matrices are re-expressed as local matrix_basis motion on the canonical bind/EditBone rest captured from the same source FBX, independently of animation samples. Static FBX rest is exported with the Action detached and identity pose, while the sole stored Action is baked separately. This is same-skeleton encoding canonicalization only; it does not make independent source rest rigs compatible, and no animation frame defines rest authority.",
        "source": {"filename": source.name, "sha256": _sha256(source), "frameRange": [source_start, source_end]},
        "sourceImportedRest": imported_rest,
        "sourceCharacterRest": canonical_rest,
        "normalized": {
            "filename": output.name,
            "sha256": _sha256(output),
            "meshIncluded": False,
            "skinIncluded": False,
            "frameRange": [normalized_start, normalized_end],
        },
        "motionRebasedToCanonicalRest": True,
        "canonicalizationOnly": True,
        "normalizationRestRebuiltFromCanonicalAuthority": True,
        "normalizationRestDerivedFromAnimationFrame": False,
        "staticFbxRestActionDetached": True,
        "staticFbxRestPoseBasisIdentity": True,
        "animationExportedFromStoredAction": True,
        "fidelityPolicy": {
            "canonicalRebaseTranslationTolerance": CANONICAL_REBASE_TRANSLATION_TOLERANCE,
            "canonicalRebaseHeadTailTolerance": CANONICAL_REBASE_HEAD_TAIL_TOLERANCE,
            "fbxSerializationTranslationTolerance": FBX_SERIALIZATION_TRANSLATION_TOLERANCE,
            "fbxSerializationHeadTailTolerance": FBX_SERIALIZATION_HEAD_TAIL_TOLERANCE,
            "rotationToleranceDegrees": ROTATION_TOLERANCE_DEGREES,
            "scaleTolerance": SCALE_TOLERANCE,
            "level1RestBasisToleranceChanged": False,
        },
        "frameOffset": frame_offset,
        "frameMapping": "normalizedFrame = sourceFrame + frameOffset",
        "fps": fps,
        "fpsNumerator": fps_numerator,
        "fpsBase": fps_base,
        "preFbxFidelity": pre_fbx_fidelity,
        "fidelity": post_fbx_fidelity,
        "restCompatibility": rest_compatibility,
        "firstAnimationPoseUsedAsRest": False,
        "animationFrameUsedAsRest": False,
        "lockedPr11RigCapturePass": True,
        "retargeting": False,
        "fuzzyMapping": False,
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
