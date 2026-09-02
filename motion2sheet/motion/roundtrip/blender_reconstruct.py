from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from motion2sheet.motion.roundtrip.blender_json_scene import build_json_scene
from motion2sheet.motion.roundtrip.fbx import encode_generated_fbx
from motion2sheet.motion.roundtrip.schema import read_json, validate_animation_document, validate_rig_document, write_canonical_json


def _argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def export_fbx_container(armature, output_path: Path) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
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


def export_fbx(armature, output_path: Path, rig: dict, animation: dict) -> Path | None:
    if rig.get("source", {}).get("format") != "FBX":
        export_fbx_container(armature, output_path)
        return None

    rig_fbx = rig.get("sourceFormat", {}).get("fbx")
    animation_fbx = animation.get("sourceFormat", {}).get("fbx")
    if rig_fbx is None or animation_fbx is None:
        raise RuntimeError("FBX reconstruction requires static sourceFormat.fbx metadata in both JSON documents")

    generic_path = output_path.with_name(output_path.stem + ".generic.fbx")
    export_fbx_container(armature, generic_path)
    derived_curves = encode_generated_fbx(
        generic_path,
        output_path,
        rig_fbx,
        animation_fbx,
        animation["frames"],
    )
    write_canonical_json(
        output_path.parent / "diagnostics" / "derived_fbx_curves.json",
        {
            "schema": "motion2sheet.diagnostics.derived-fbx-curves",
            "version": 1,
            "note": "Derived only from animation.frames + static FBX metadata; not canonical authority.",
            "sampleKeyTimes": animation_fbx["sampleKeyTimes"],
            "curves": derived_curves,
        },
    )
    return generic_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rig", required=True)
    parser.add_argument("--animation", required=True)
    parser.add_argument("--blend-output", required=True)
    parser.add_argument("--fbx-output", required=True)
    args = parser.parse_args(_argv())
    rig = validate_rig_document(read_json(Path(args.rig)))
    animation = validate_animation_document(read_json(Path(args.animation)), rig)
    blend_output = Path(args.blend_output).resolve()
    fbx_output = Path(args.fbx_output).resolve()
    blend_output.parent.mkdir(parents=True, exist_ok=True)
    fbx_output.parent.mkdir(parents=True, exist_ok=True)
    armature, _action = build_json_scene(rig, animation)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_output), check_existing=False)
    generic_path = export_fbx(armature, fbx_output, rig, animation)
    generic_text = f"; generic={generic_path}" if generic_path else ""
    print(f"motion2sheet: JSON-only reconstruction OK -> {blend_output}; {fbx_output}{generic_text}")


if __name__ == "__main__":
    main()
