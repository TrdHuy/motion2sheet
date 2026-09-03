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

from motion2sheet.motion.model_render.blender_level1 import export_armature_only_fbx
from motion2sheet.motion.model_render.blender_rest_authority import (
    capture_character_rig_document,
    capture_imported_rest_rig_document,
)
from motion2sheet.motion.roundtrip.blender_common import (
    capture_rig_document,
    import_source,
    integer_action_range,
    scene_fps,
)
from motion2sheet.motion.roundtrip.fbx import extract_fbx_metadata_and_diagnostics
from motion2sheet.motion.roundtrip.schema import validate_rig_document
from motion2sheet.motion.skin import validate_level1_rig_compatibility

TRANSLATION_TOLERANCE = 1e-5
HEAD_TAIL_TOLERANCE = 1e-5
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
        max_translation <= TRANSLATION_TOLERANCE
        and max_head_tail <= HEAD_TAIL_TOLERANCE
        and max_rotation <= ROTATION_TOLERANCE_DEGREES
        and max_scale <= SCALE_TOLERANCE
    )
    return {
        "pass": passed,
        "boneCount": len(parents),
        "exactBoneNames": True,
        "exactHierarchy": True,
        "sourceFrameRange": [source_start, source_end],
        "normalizedFrameRange": [source_start + frame_offset, source_end + frame_offset],
        "frameOffset": frame_offset,
        "frameCount": source_end - source_start + 1,
        "maxWorldTranslationError": max_translation,
        "translationTolerance": TRANSLATION_TOLERANCE,
        "worstWorldTranslation": worst_translation,
        "maxHeadTailError": max_head_tail,
        "headTailTolerance": HEAD_TAIL_TOLERANCE,
        "worstHeadTail": worst_head_tail,
        "maxWorldRotationErrorDegrees": max_rotation,
        "rotationToleranceDegrees": ROTATION_TOLERANCE_DEGREES,
        "worstWorldRotation": worst_rotation,
        "maxWorldScaleError": max_scale,
        "scaleTolerance": SCALE_TOLERANCE,
        "worstWorldScale": worst_scale,
    }


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

    armature, action = import_source(source)
    source_start, source_end = integer_action_range(action)
    source_frame_count = source_end - source_start + 1
    fps, fps_numerator, fps_base = scene_fps(bpy.context.scene)
    parents = {bone.name: bone.parent.name if bone.parent else None for bone in armature.data.bones}

    # Character rest capture reads only EditBone/static FBX authority. The source action
    # is used here solely as motion authority for the motion-only FBX; it never defines
    # character rest. Keep source armature rest and source animation together so Blender
    # can re-encode the FBX representation without any rest reconstruction step.
    _imported_rig, imported_rest = capture_imported_rest_rig_document(source, armature)
    reference = _capture_pose(armature, source_start, source_end)
    canonical_source_rig, canonical_rest = capture_character_rig_document(source, armature)

    # Export the imported armature directly. Rebuilding EditBones from JSON before this
    # step was the source of a 5.89-degree Head roll representation change. Direct export
    # preserves the source bind/edit rest while Blender removes only importer-level FBX
    # numerical encoding differences. No first-frame rest, mapping, or retargeting occurs.
    export_armature_only_fbx(armature, output)

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
    actual = _capture_pose(normalized_armature, normalized_start, normalized_end)
    fidelity = _compare(reference, actual, parents, source_start, source_end, frame_offset)

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
        raise RuntimeError("locked Contract B rig capture changed the normalized bone count")

    # Both sides are now clip-independent representations of the same static rest:
    # character = EditBone/bind authority canonicalized with an identity-only carrier;
    # motion = the original imported armature rest re-encoded with its actual motion.
    # Level-1 remains strict at the existing 0.001-degree tolerance.
    rest_compatibility = validate_level1_rig_compatibility(normalized_rig, canonical_source_rig)

    report = {
        "schema": "motion2sheet.diagnostics.level1-motion-source-normalization",
        "version": 1,
        "reason": "The source armature is exported directly so its FBX bind/edit rest is preserved while its real Action remains motion authority only. Character rest is independently canonicalized from EditBone/static bind data with an identity-only encoding carrier. No animation frame is used as rest authority and no retargeting occurs.",
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
        "normalizationRestRebuilt": False,
        "frameOffset": frame_offset,
        "frameMapping": "normalizedFrame = sourceFrame + frameOffset",
        "fps": fps,
        "fpsNumerator": fps_numerator,
        "fpsBase": fps_base,
        "fidelity": fidelity,
        "restCompatibility": rest_compatibility,
        "firstAnimationPoseUsedAsRest": False,
        "animationFrameUsedAsRest": False,
        "lockedPr11RigCapturePass": True,
        "retargeting": False,
        "fuzzyMapping": False,
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    if not fidelity["pass"]:
        raise RuntimeError(f"motion-source normalization fidelity failed: {fidelity}")
    print(json.dumps(report, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
