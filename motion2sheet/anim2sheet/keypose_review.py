"""Fast four-key-pose review orchestration.

This path intentionally renders only F1/F6/F7/F8. It is an architecture proof
for deterministic arm control and is not a replacement for the later full
16-frame animation review.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

import json5

from .common.output.packer import compose_sheet

REVIEW_FRAMES = [1, 6, 7, 8]


def blender_executable(name: str) -> str:
    value = shutil.which(name) if Path(name).name == name else name
    if not value:
        raise RuntimeError(f"Blender executable not found: {name}")
    return str(value)


def load_profile(path: Path) -> tuple[dict, Path, dict]:
    profile = json5.loads(path.read_text(encoding="utf-8"))
    ref_path = Path(profile["poseReference"])
    if not ref_path.is_absolute():
        ref_path = path.parent / ref_path
    reference = json.loads(ref_path.read_text(encoding="utf-8"))
    return profile, ref_path.resolve(), reference


def run(args) -> int:
    profile_path = Path(args.profile).resolve()
    joint_path = Path(args.joint_contract).resolve()
    output = Path(args.output).resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    profile, ref_path, reference = load_profile(profile_path)
    source = dict(profile)
    source["generator"] = "fast-keypose-deterministic-joint-fk-v1"
    source["reviewMode"] = "fast-keypose-review"
    source["reviewFrames"] = REVIEW_FRAMES
    source["poseReferenceSource"] = str(ref_path)
    source["poseReferenceData"] = reference
    source["armJointContractSource"] = str(joint_path)
    (output / "source.json").write_text(
        json.dumps(source, indent=2) + "\n", encoding="utf-8"
    )

    blender = blender_executable(args.blender)
    entry = Path(__file__).resolve().with_name("blender_keypose_entry.py")
    subprocess.run(
        [
            blender,
            "--background",
            "--factory-startup",
            "--python",
            str(entry),
            "--",
            "--spec",
            str((output / "source.json").resolve()),
            "--joint-contract",
            str(joint_path),
            "--output",
            str(output),
        ],
        check=True,
        timeout=240,
    )

    skeleton_entry = Path(__file__).resolve().with_name("blender_skeleton_viewport.py")
    command = [
        blender,
        str((output / "source.blend").resolve()),
        "--python",
        str(skeleton_entry),
        "--",
        "--output",
        str((output / "skeleton_frames").resolve()),
        "--rig-output",
        str(output),
        "--frames",
        ",".join(str(v) for v in REVIEW_FRAMES),
        "--skip-rig-docs",
    ]
    xvfb = shutil.which("xvfb-run")
    if xvfb:
        command = [xvfb, "-a", *command]
    subprocess.run(command, check=True, timeout=120)

    object_frames = [output / "frames" / f"{frame:02d}.png" for frame in REVIEW_FRAMES]
    skeleton_frames = [output / "skeleton_frames" / f"{frame:02d}.png" for frame in REVIEW_FRAMES]
    for path in [*object_frames, *skeleton_frames]:
        if not path.is_file():
            raise RuntimeError(f"key-pose review output missing: {path}")
    compose_sheet(object_frames, output / "object_keyposes.png", columns=4)
    compose_sheet(skeleton_frames, output / "skeleton_keyposes.png", columns=4)

    metadata = {
        "tool": "anim2sheet",
        "mode": "fast-keypose-review",
        "reviewFrames": REVIEW_FRAMES,
        "armControl": "deterministic_joint_fk",
        "legControl": "ik_with_explicit_knee_poles",
        "torsoControl": "fk",
        "weaponBinding": "two_hand_joint_grip",
        "objectRenderer": "blender-workbench-fast-review",
        "objectPreview": "object_keyposes.png",
        "skeletonPreview": "skeleton_keyposes.png",
        "debug": "motion_debug.json",
        "sourceBlend": "source.blend",
    }
    (output / "metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(f"anim2sheet fast key-pose review OK -> {output}", flush=True)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--joint-contract", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--blender", default="blender")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (
        RuntimeError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        OSError,
        ValueError,
    ) as exc:
        print(f"anim2sheet keypose review: {exc}", flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
