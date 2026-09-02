from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from motion2sheet.motion.roundtrip.blender_common import world_pose_snapshot
from motion2sheet.motion.roundtrip.blender_json_scene import build_json_scene
from motion2sheet.motion.roundtrip.schema import read_json, validate_animation_document, validate_rig_document


def _argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rig", required=True)
    parser.add_argument("--animation", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(_argv())

    rig = validate_rig_document(read_json(Path(args.rig)))
    animation = validate_animation_document(read_json(Path(args.animation)), rig)
    armature, _action = build_json_scene(rig, animation)
    frames = tuple(int(entry["frame"]) for entry in animation["frames"])
    pose_data = {
        "frameRange": list(animation["frameRange"]),
        "frames": {str(frame): world_pose_snapshot(armature, frame) for frame in frames},
    }

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(pose_data, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(
        "motion2sheet: canonical JSON pose materialized; "
        f"bones={len(rig['bones'])}, frames={len(frames)} -> {output}"
    )


if __name__ == "__main__":
    main()
