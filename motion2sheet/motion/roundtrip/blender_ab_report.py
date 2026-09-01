from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from motion2sheet.motion.roundtrip.blender_verify import compare_local, compare_structure, compare_world, load_blend, load_source
from motion2sheet.motion.roundtrip.schema import read_json, validate_animation_document, validate_rig_document


def _argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def _stage(source, target, frames):
    structure = compare_structure(source, target)
    local = compare_local(source, target, frames)
    world = compare_world(source, target, frames)
    return {
        "pass": bool(structure["pass"] and local["pass"] and world["pass"]),
        "structure": structure,
        "local": local,
        "world": world,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--rig", required=True)
    parser.add_argument("--animation", required=True)
    parser.add_argument("--blend", required=True)
    parser.add_argument("--generic-fbx", required=True)
    parser.add_argument("--encoded-fbx", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(_argv())

    rig = validate_rig_document(read_json(Path(args.rig)))
    animation = validate_animation_document(read_json(Path(args.animation)), rig)
    frames = list(range(animation["frameRange"][0], animation["frameRange"][1] + 1))

    source = load_source(Path(args.source).resolve(), frames)
    blend = load_blend(Path(args.blend).resolve(), frames)
    generic = load_source(Path(args.generic_fbx).resolve(), frames)
    encoded = load_source(Path(args.encoded_fbx).resolve(), frames)

    result = {
        "schema": "motion2sheet.roundtrip-ab-report",
        "version": 1,
        "authority": "animation.frames[].bones",
        "A_frames_to_reconstructed_blend": _stage(source, blend, frames),
        "B_frames_to_generic_blender_fbx_reimport": _stage(source, generic, frames),
        "C_frames_plus_static_fbx_metadata_to_encoded_fbx_reimport": _stage(source, encoded, frames),
    }
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
