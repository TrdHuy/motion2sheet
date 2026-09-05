from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

import bpy

from motion2sheet.motion.model_render.blender_helpers import (
    import_geometry_glb,
    mesh_layout,
    playback_diagnostics,
    reconstruct_skin,
    setup_camera_and_render,
)
from motion2sheet.motion.roundtrip.blender_json_scene import build_action, build_armature
from motion2sheet.motion.roundtrip.schema import read_json, validate_animation_document, validate_rig_document
from motion2sheet.motion.skin import compare_skin_bindings, validate_level1_rig_compatibility, validate_skin_document, verify_model_identity


def _argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    args = parser.parse_args(_argv())
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    output = Path(request["output"])
    diagnostics = output / "diagnostics"
    diagnostics.mkdir(parents=True, exist_ok=True)

    model_path = Path(request["modelPath"])
    character_rig = validate_rig_document(read_json(Path(request["characterRigPath"])))
    animation_rig = validate_rig_document(read_json(Path(request["animationRigPath"])))
    animation = validate_animation_document(read_json(Path(request["animationPath"])), animation_rig)
    skin = validate_skin_document(read_json(Path(request["skinPath"])), character_rig)
    compatibility = validate_level1_rig_compatibility(animation_rig, character_rig)
    if compatibility != request["compatibility"]:
        raise RuntimeError("Level-1 compatibility changed between public validation and Blender execution")
    roots = [bone["name"] for bone in character_rig["bones"] if bone["parent"] is None]
    if len(roots) != 1:
        raise RuntimeError(f"Level-1 real-model renderer requires exactly one root bone; found {roots}")
    root_bone = roots[0]
    request["rootBone"] = root_bone

    model_objects = import_geometry_glb(model_path)
    layout = mesh_layout(model_objects)
    verify_model_identity(skin, model_path, layout)
    model_identity = {
        "pass": True,
        "sameMeshObjects": sorted(row["object"] for row in layout) == sorted(mesh["object"] for mesh in skin["meshes"]),
        "sameVertexCounts": all(
            next(row for row in layout if row["object"] == mesh["object"])["vertexCount"] == mesh["vertexCount"]
            for mesh in skin["meshes"]
        ),
        "sameVertexOrder": all(
            next(row for row in layout if row["object"] == mesh["object"])["vertexOrderHash"] == mesh["vertexOrderHash"]
            for mesh in skin["meshes"]
        ),
        "meshCount": len(layout),
        "vertexCount": sum(row["vertexCount"] for row in layout),
        "layout": layout,
    }
    _write(diagnostics / "model_identity.json", model_identity)

    character_armature = build_armature(character_rig)
    reconstructed_skin = reconstruct_skin(model_objects, character_armature, skin)
    skin_report = compare_skin_bindings(skin, reconstructed_skin, tolerance=float(request["skinWeightTolerance"]))
    _write(diagnostics / "skin_reconstruction.json", skin_report)
    if not skin_report["pass"]:
        raise RuntimeError(
            "skin reconstruction exceeded strict tolerance; "
            f"maxWeightDelta={skin_report['maxWeightDelta']:.12g} tolerance={request['skinWeightTolerance']:.12g} "
            f"worst={skin_report.get('worst')}"
        )

    reference_rig = copy.deepcopy(animation_rig)
    reference_rig["armatureObject"] = copy.deepcopy(reference_rig["armatureObject"])
    reference_rig["armatureObject"]["name"] = "SourceAnimationReference"
    reference_rig["armatureObject"]["dataName"] = "SourceAnimationReference"
    reference_armature = build_armature(reference_rig)
    # Keep the oracle out of renders, but do not hide it from the viewport/depsgraph:
    # playback_diagnostics changes frames and requires the reference pose to evaluate.
    reference_armature.hide_render = True

    build_action(character_armature, animation)
    build_action(reference_armature, animation)
    scene = bpy.context.scene
    scene.render.fps = int(animation["fpsNumerator"])
    scene.render.fps_base = float(animation["fpsBase"])
    scene.frame_start = int(animation["frameRange"][0])
    scene.frame_end = int(animation["frameRange"][1])

    # Fail closed on motion fidelity before spending time rendering all frames.
    playback = playback_diagnostics(reference_armature, character_armature, animation, root_bone)
    _write(diagnostics / "playback.json", playback)
    if not playback["pass"]:
        raise RuntimeError(f"Motion JSON Level-1 playback fidelity failed: {playback}")

    setup_camera_and_render(request, character_armature)
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "source.blend"))
    print(json.dumps({"rootBone": root_bone, "skinReconstruction": skin_report, "playback": playback, "compatibility": compatibility}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
