from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

import bpy

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from motion2sheet.motion.extract.blender import activate_animation, find_armature
from motion2sheet.motion.roundtrip.blender_reconstruct import shift_action_frames
from motion2sheet.motion.roundtrip.blender_verify import (
    compare_local,
    compare_structure,
    compare_world,
    load_source,
)
from motion2sheet.motion.roundtrip.schema import read_json, validate_animation_document, validate_rig_document

AXES = ("X", "Y", "Z", "-X", "-Y", "-Z")


def _argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def _axis_letter(axis: str) -> str:
    return axis[-1]


def export_candidate(blend_path: Path, output_path: Path, primary: str, secondary: str) -> None:
    bpy.ops.wm.open_mainfile(filepath=str(blend_path))
    armature = find_armature()
    action = activate_animation(armature)
    scene = bpy.context.scene
    original_start = scene.frame_start
    original_end = scene.frame_end
    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature

    # Match the canonical exporter timeline convention: invert Blender FBX
    # importer's default +1 animation offset while writing the test FBX.
    shift_action_frames(action, -1.0)
    scene.frame_start = original_start - 1
    scene.frame_end = original_end - 1
    try:
        bpy.ops.export_scene.fbx(
            filepath=str(output_path),
            use_selection=True,
            object_types={"ARMATURE"},
            apply_unit_scale=True,
            apply_scale_options="FBX_SCALE_NONE",
            use_space_transform=True,
            bake_space_transform=False,
            axis_forward="-Z",
            axis_up="Y",
            primary_bone_axis=primary,
            secondary_bone_axis=secondary,
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
    finally:
        shift_action_frames(action, 1.0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--rig", required=True)
    parser.add_argument("--animation", required=True)
    parser.add_argument("--blend", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(_argv())

    rig = validate_rig_document(read_json(Path(args.rig)))
    animation = validate_animation_document(read_json(Path(args.animation)), rig)
    frames = list(range(animation["frameRange"][0], animation["frameRange"][1] + 1))
    source = load_source(Path(args.source).resolve(), frames)
    blend_path = Path(args.blend).resolve()
    results = []

    scratch = Path(tempfile.mkdtemp(prefix="motion2sheet-fbx-axis-probe-"))
    try:
        for primary in AXES:
            for secondary in AXES:
                if _axis_letter(primary) == _axis_letter(secondary):
                    continue
                candidate = scratch / f"{primary.replace('-', 'neg')}_{secondary.replace('-', 'neg')}.fbx"
                entry = {"primary": primary, "secondary": secondary}
                try:
                    export_candidate(blend_path, candidate, primary, secondary)
                    target = load_source(candidate, frames)
                    structure = compare_structure(source, target)
                    local = compare_local(source, target, frames)
                    world = compare_world(source, target, frames)
                    entry.update({"structure": structure, "local": local, "world": world})
                    entry["score"] = [
                        0 if structure.get("frameRangeExact") else 1,
                        float(structure.get("maxRestAngularErrorDeg", 1e30)),
                        float(structure.get("maxRestTranslationError", 1e30)),
                        float(local.get("maxAngularErrorDeg", 1e30)),
                        float(local.get("maxTranslationError", 1e30)),
                        float(world.get("maxWorldError", 1e30)),
                    ]
                except Exception as exc:
                    entry.update({"error": f"{type(exc).__name__}: {exc}", "score": [1, 1e30, 1e30, 1e30, 1e30, 1e30]})
                results.append(entry)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    results.sort(key=lambda item: item["score"])
    document = {
        "schema": "motion2sheet.fbx-axis-probe",
        "version": 1,
        "candidateCount": len(results),
        "best": results[0] if results else None,
        "results": results,
    }
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"candidateCount": len(results), "best": document["best"]}, indent=2))


if __name__ == "__main__":
    main()
