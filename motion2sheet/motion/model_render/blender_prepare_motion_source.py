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

from motion2sheet.motion.roundtrip.blender_common import (
    capture_rig_document,
    import_source,
    integer_action_range,
    scene_fps,
)
from motion2sheet.motion.roundtrip.schema import validate_rig_document

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


def _export_armature_only(armature, output: Path) -> None:
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


def _compare(reference, actual, parents, start: int, end: int) -> dict[str, object]:
    max_translation = max_head_tail = max_rotation = max_scale = 0.0
    worst_translation = worst_head_tail = worst_rotation = worst_scale = None
    for frame in range(start, end + 1):
        expected_rows = reference[frame]
        actual_rows = actual[frame]
        if set(expected_rows) != set(actual_rows):
            raise RuntimeError(
                f"normalized motion bone set mismatch at frame {frame}: "
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
            if translation > max_translation:
                max_translation, worst_translation = translation, {"frame": frame, "bone": name}
            if head_tail > max_head_tail:
                max_head_tail, worst_head_tail = head_tail, {"frame": frame, "bone": name, "headError": head, "tailError": tail}
            if rotation > max_rotation:
                max_rotation, worst_rotation = rotation, {"frame": frame, "bone": name}
            if scale > max_scale:
                max_scale, worst_scale = scale, {"frame": frame, "bone": name}
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
        "frameRange": [start, end],
        "frameCount": end - start + 1,
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
    start, end = integer_action_range(action)
    fps, fps_numerator, fps_base = scene_fps(bpy.context.scene)
    parents = {bone.name: bone.parent.name if bone.parent else None for bone in armature.data.bones}
    reference = _capture_pose(armature, start, end)
    _export_armature_only(armature, output)

    normalized_armature, normalized_action = import_source(output)
    normalized_start, normalized_end = integer_action_range(normalized_action)
    if (normalized_start, normalized_end) != (start, end):
        raise RuntimeError(
            f"normalized motion frame range changed: source={[start,end]} normalized={[normalized_start,normalized_end]}"
        )
    normalized_parents = {bone.name: bone.parent.name if bone.parent else None for bone in normalized_armature.data.bones}
    if normalized_parents != parents:
        raise RuntimeError("normalized motion hierarchy changed")
    actual = _capture_pose(normalized_armature, start, end)
    fidelity = _compare(reference, actual, parents, start, end)

    # This is the critical proof that the locked PR #11 rig capture can consume the normalized copy
    # without changing its tolerance or implementation.
    normalized_rig = validate_rig_document(capture_rig_document(output, normalized_armature))
    if len(normalized_rig["bones"]) != len(parents):
        raise RuntimeError("locked Contract B rig capture changed the normalized bone count")

    report = {
        "schema": "motion2sheet.diagnostics.level1-motion-source-normalization",
        "version": 1,
        "reason": "The release With-Skin FBX imports with tiny non-TRS numerical rest shear that the locked PR #11 Contract B exporter correctly rejects. This PR12-local armature-only FBX is accepted only after all-frame world-pose equivalence passes.",
        "source": {"filename": source.name, "sha256": _sha256(source)},
        "normalized": {"filename": output.name, "sha256": _sha256(output), "meshIncluded": False, "skinIncluded": False},
        "fps": fps,
        "fpsNumerator": fps_numerator,
        "fpsBase": fps_base,
        "fidelity": fidelity,
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
