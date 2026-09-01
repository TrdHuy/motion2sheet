from __future__ import annotations

import argparse
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from motion2sheet.motion.roundtrip.blender_common import capture_animation_document, capture_rig_document, import_source
from motion2sheet.motion.roundtrip.fbx import extract_fbx_authority
from motion2sheet.motion.roundtrip.schema import validate_animation_document, validate_rig_document, write_canonical_json


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

    armature, action = import_source(input_path)
    rig = capture_rig_document(input_path, armature)
    animation = capture_animation_document(input_path, armature, action, rig)

    if input_path.suffix.lower() == ".fbx":
        rig_fbx, animation_fbx = extract_fbx_authority(
            input_path,
            [bone["name"] for bone in rig["bones"]],
            animation["frameCount"],
        )
        rig["sourceFormat"] = {"fbx": rig_fbx}
        animation["sourceFormat"] = {"fbx": animation_fbx}

    rig = validate_rig_document(rig)
    animation = validate_animation_document(animation, rig)
    write_canonical_json(output / "rig.json", rig)
    write_canonical_json(output / "animation.json", animation)
    print(
        f"motion2sheet: exported source-authority JSON; bones={len(rig['bones'])}, "
        f"frames={animation['frameCount']}, fps={animation['fps']} -> {output}"
    )


if __name__ == "__main__":
    main()
