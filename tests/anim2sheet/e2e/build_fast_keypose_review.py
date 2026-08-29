from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import json5

from motion2sheet.anim2sheet.common.output.packer import compose_sheet


ROOT = Path(__file__).resolve().parents[3]
PROFILE = ROOT / "profiles/anim2sheet/swordsman/gale_slash.json5"
REFERENCE = ROOT / "profiles/anim2sheet/swordsman/gale_slash_pose_reference.json"
JOINTS = ROOT / "profiles/anim2sheet/swordsman/gale_slash_arm_joint_keyposes.json"
BLENDER_ENTRY = ROOT / "motion2sheet/anim2sheet/blender_keypose_entry.py"
SKELETON_ENTRY = ROOT / "motion2sheet/anim2sheet/blender_skeleton_viewport.py"
REVIEW_FRAMES = [1, 6, 7, 8]


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: build_fast_keypose_review.py OUTPUT_DIR")
    output = Path(sys.argv[1]).resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    profile = json5.loads(PROFILE.read_text(encoding="utf-8"))
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    joint_contract = json.loads(JOINTS.read_text(encoding="utf-8"))
    if joint_contract.get("reviewFrames") != REVIEW_FRAMES:
        raise RuntimeError("joint contract reviewFrames must be [1, 6, 7, 8]")

    source = dict(profile)
    source["mode"] = "fast-keypose-review"
    source["reviewFrames"] = REVIEW_FRAMES
    source["poseReferenceData"] = reference
    source["poseReferenceSource"] = str(REFERENCE)
    source_path = output / "source.json"
    source_path.write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8")

    subprocess.run([
        "blender", "--background", "--factory-startup",
        "--python", str(BLENDER_ENTRY), "--",
        "--spec", str(source_path),
        "--joint-contract", str(JOINTS),
        "--output", str(output),
    ], check=True, cwd=ROOT)

    skeleton_dir = output / "skeleton_frames"
    command = [
        "blender", str(output / "source.blend"),
        "--python", str(SKELETON_ENTRY), "--",
        "--output", str(skeleton_dir),
        "--rig-output", str(output),
        "--frames", ",".join(str(v) for v in REVIEW_FRAMES),
    ]
    xvfb = shutil.which("xvfb-run")
    if xvfb:
        command = [xvfb, "-a", *command]
    subprocess.run(command, check=True, cwd=ROOT)

    object_frames = [output / "frames" / f"{v:02d}.png" for v in REVIEW_FRAMES]
    skeleton_frames = [skeleton_dir / f"{v:02d}.png" for v in REVIEW_FRAMES]
    compose_sheet(object_frames, output / "object_keyposes.png", columns=4)
    compose_sheet(skeleton_frames, output / "skeleton_keyposes.png", columns=4)

    metadata = {
        "tool": "anim2sheet",
        "mode": "fast-keypose-review",
        "reviewFrames": REVIEW_FRAMES,
        "armControl": "deterministic_joint_fk",
        "torsoControl": "fk",
        "legControl": "ik_with_explicit_knee_poles",
        "weaponBinding": "two_hand_joint_axis",
        "objectPreview": "object_keyposes.png",
        "skeletonPreview": "skeleton_keyposes.png",
        "debug": "motion_debug.json",
        "fullAnimationRendered": False,
    }
    (output / "keypose_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(f"fast key-pose review built -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
