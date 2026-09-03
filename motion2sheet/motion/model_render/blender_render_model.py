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
from motion2sheet.motion.model_render.blender_rest_basis import (
    build_rest_basis_adapted_action,
    build_static_rest_basis_adapter,
    rest_basis_motion_fidelity,
)
from motion2sheet.motion.roundtrip.blender_json_scene import build_action, build_armature
from motion2sheet.motion.roundtrip.schema import read_json, validate_animation_document, validate_rig_document
from motion2sheet.motion.skin import (
    compare_skin_bindings,
    diagnose_level1_rig_compatibility,
    validate_level1_rig_compatibility,
    validate_level2_rest_basis_eligibility,
    validate_skin_document,
    verify_model_identity,
)


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
    compatibility = request["compatibility"]
    level = int(compatibility["compatibilityLevel"])
    if level not in (1, 2):
        raise RuntimeError(f"unsupported runtime compatibility level: {level}")

    current_level1 = diagnose_level1_rig_compatibility(animation_rig, character_rig)
    if current_level1 != compatibility["level1"]:
        raise RuntimeError("rig compatibility changed between public validation and Blender execution")
    if level == 1:
        strict_level1 = validate_level1_rig_compatibility(animation_rig, character_rig)
        if strict_level1 != compatibility["level1"] or compatibility["adaptationApplied"]:
            raise RuntimeError("Level-1 runtime selection is inconsistent with public validation")
    else:
        if current_level1["pass"]:
            raise RuntimeError("Level-2 must not run when Level-1 already passes")
        strict_level2 = validate_level2_rest_basis_eligibility(animation_rig, character_rig)
        if strict_level2 != compatibility["level2Eligibility"]:
            raise RuntimeError("Level-2 eligibility changed between public validation and Blender execution")
        if not compatibility["adaptationApplied"] or compatibility["adaptationType"] != "rest-basis":
            raise RuntimeError("Level-2 runtime requires explicit rest-basis adaptation selection")

    roots = [bone["name"] for bone in character_rig["bones"] if bone["parent"] is None]
    if len(roots) != 1:
        raise RuntimeError(f"real-model renderer requires exactly one root bone; found {roots}")
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
    reference_rig["armatureObject"]["name"] = "ContractBAnimationReference"
    reference_rig["armatureObject"]["dataName"] = "ContractBAnimationReference"
    reference_armature = build_armature(reference_rig)
    reference_armature.hide_render = True

    if level == 1:
        build_action(character_armature, animation)
        build_action(reference_armature, animation)
        playback = playback_diagnostics(reference_armature, character_armature, animation, root_bone)
        if not playback["pass"]:
            _write(diagnostics / "playback.json", playback)
            raise RuntimeError(f"Contract B Level-1 playback fidelity failed: {playback}")
    else:
        # Static basis authority is captured before either armature receives animation.
        static_adapter = build_static_rest_basis_adapter(reference_armature, character_armature)
        static_adapter["sourceRestFingerprint"] = compatibility["level2Eligibility"]["sourceRestFingerprint"]
        static_adapter["targetRestFingerprint"] = compatibility["level2Eligibility"]["targetRestFingerprint"]
        static_adapter["level1RestBasisMismatchCount"] = compatibility["level1"]["restBasisMismatchCount"]
        static_adapter["level1MaxRestBasisErrorDegrees"] = compatibility["level1"]["maxRestBasisErrorDegrees"]
        static_adapter["level1WorstRestBasisBone"] = compatibility["level1"]["worstRestBasisBone"]
        build_action(reference_armature, animation)
        build_rest_basis_adapted_action(reference_armature, character_armature, animation, static_adapter)
        playback = rest_basis_motion_fidelity(reference_armature, character_armature, animation, root_bone, static_adapter)
        adaptation_report = {
            **static_adapter,
            "compatibilityLevel": 2,
            "adaptationApplied": True,
            "contractBMutated": False,
            "runtimeTransformsDerivedFrom": ["animation_rig.json", "animation.json", "character_rig.json"],
            "runtimeTransformsAreCanonicalMotionAuthority": False,
            "fidelity": playback,
        }
        _write(diagnostics / "rest_basis_adaptation.json", adaptation_report)
        if not playback["pass"]:
            _write(diagnostics / "playback.json", playback)
            raise RuntimeError(f"Contract B Level-2 rest-basis fidelity failed: {playback}")

    _write(diagnostics / "playback.json", playback)
    scene = bpy.context.scene
    scene.render.fps = int(animation["fpsNumerator"])
    scene.render.fps_base = float(animation["fpsBase"])
    scene.frame_start = int(animation["frameRange"][0])
    scene.frame_end = int(animation["frameRange"][1])

    setup_camera_and_render(request, character_armature)
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "source.blend"))
    print(
        json.dumps(
            {
                "rootBone": root_bone,
                "skinReconstruction": skin_report,
                "playback": playback,
                "compatibilityLevel": level,
                "adaptationApplied": bool(compatibility["adaptationApplied"]),
                "adaptationType": compatibility["adaptationType"],
            },
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
