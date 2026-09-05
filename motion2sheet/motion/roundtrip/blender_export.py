from __future__ import annotations

import argparse
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from motion2sheet.motion.roundtrip.blender_common import capture_animation_document, capture_rig_document, import_source
from motion2sheet.motion.roundtrip.fbx import (
    capture_blender_fbx_pose_adapters,
    extract_fbx_metadata_and_diagnostics,
)
from motion2sheet.motion.roundtrip.schema import validate_animation_document, validate_rig_document, write_canonical_json
from motion2sheet.motion.roundtrip.native_timing import (
    extract_bvh_native_timing,
    validate_bvh_native_timing,
    validate_fbx_native_timing,
)


def _argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(_argv())
    input_path = Path(args.input).resolve()
    output = Path(args.output).resolve()
    if input_path.suffix.lower() not in {".fbx", ".bvh"}:
        raise RuntimeError("Round-trip POC v1 supports FBX/BVH source animation files")

    if input_path.suffix.lower() == ".fbx":
        with capture_blender_fbx_pose_adapters() as encoding_adapters:
            armature, action = import_source(input_path)
    else:
        encoding_adapters = {}
        armature, action = import_source(input_path)

    rig = capture_rig_document(input_path, armature)
    animation = capture_animation_document(input_path, armature, action, rig)
    if input_path.suffix.lower() == ".fbx":
        rig_fbx, animation_fbx, original_curves = extract_fbx_metadata_and_diagnostics(
            input_path,
            [bone["name"] for bone in rig["bones"]],
            animation["frameCount"],
            action_name=action.name,
        )
        for bone_name, adapter in encoding_adapters.items():
            if bone_name in rig_fbx["bones"]:
                rig_fbx["bones"][bone_name]["encodingAdapter"] = adapter

        rig["sourceFormat"] = {"fbx": rig_fbx}
        animation["sourceFormat"] = {"fbx": animation_fbx}
        timing = validate_fbx_native_timing(
            animation_fbx,
            global_settings=rig_fbx["globalSettings"],
            frame_count=animation["frameCount"],
            fps=animation["fps"],
        )
        animation["durationSeconds"] = timing["durationSeconds"]
        write_canonical_json(
            output / "diagnostics" / "original_fbx_curves.json",
            {
                "schema": "motion2sheet.diagnostics.original-fbx-curves",
                "version": 1,
                "sourceSha256": rig["source"]["sha256"],
                "note": "Diagnostic oracle only. Canonical reconstruction must not read this file.",
                "sampleKeyTimes": animation_fbx["sampleKeyTimes"],
                "curves": original_curves,
            },
        )
    else:
        animation_bvh = extract_bvh_native_timing(input_path)
        animation["sourceFormat"] = {"bvh": animation_bvh}
        timing = validate_bvh_native_timing(
            animation_bvh,
            frame_count=animation["frameCount"],
            fps=animation["fps"],
        )
        animation["durationSeconds"] = timing["durationSeconds"]

    rig = validate_rig_document(rig)
    animation = validate_animation_document(animation, rig)
    write_canonical_json(output / "rig.json", rig)
    write_canonical_json(output / "animation.json", animation)
    print(
        f"motion2sheet: exported source-authority JSON; bones={len(rig['bones'])}, "
        f"frames={animation['frameCount']}, fps={animation['fps']}, "
        f"durationSeconds={animation['durationSeconds']} -> {output}; "
        f"fbxEncodingAdapters={len(encoding_adapters)}"
    )


if __name__ == "__main__":
    main()
