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
from PIL import Image, ImageDraw

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


def write_authority_overlays(output: Path) -> None:
    diagnostic = json.loads((output / "reopen_debug.json").read_text(encoding="utf-8"))
    by_frame = {int(row["frame"]): row for row in diagnostic["framesData"]}
    overlay_dir = output / "overlay_frames"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    overlay_paths = []
    for frame in REVIEW_FRAMES:
        source_path = output / "frames" / f"{frame:02d}.png"
        image = Image.open(source_path).convert("RGBA")
        draw = ImageDraw.Draw(image, "RGBA")
        for segment in by_frame[frame]["bonePixelSegments"]:
            head = tuple(segment["headPx"])
            tail = tuple(segment["tailPx"])
            draw.line([head, tail], fill=(255, 40, 40, 235), width=4)
            radius = 4
            for point in (head, tail):
                x, y = point
                draw.ellipse(
                    [x - radius, y - radius, x + radius, y + radius],
                    fill=(255, 230, 40, 245),
                )
        path = overlay_dir / f"{frame:02d}.png"
        image.save(path)
        image.close()
        overlay_paths.append(path)
    compose_sheet(overlay_paths, output / "object_skeleton_overlay.png", columns=4)


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
    source_path = output / "source.json"
    source_path.write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8")

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
            str(source_path.resolve()),
            "--joint-contract",
            str(joint_path),
            "--output",
            str(output),
        ],
        check=True,
        timeout=240,
    )

    blend_path = output / "source.blend"
    debug_path = output / "motion_debug.json"
    if not blend_path.is_file():
        raise RuntimeError("key-pose Blender stage did not produce source.blend")
    if not debug_path.is_file():
        raise RuntimeError("key-pose Blender stage did not produce motion_debug.json")

    object_frames = [output / "frames" / f"{frame:02d}.png" for frame in REVIEW_FRAMES]
    for path in object_frames:
        if not path.is_file():
            raise RuntimeError(f"key-pose object output missing: {path}")

    # Reopen the saved blend in a fresh Blender process before any later
    # diagnostic renderer touches it. This proves keyframe/save persistence and
    # samples proxy deformation from the authoritative saved file.
    reopen_entry = Path(__file__).resolve().with_name("blender_reopen_verify.py")
    subprocess.run(
        [
            blender,
            "--background",
            str(blend_path.resolve()),
            "--python",
            str(reopen_entry),
            "--",
            "--output",
            str(output),
            "--contract",
            str((output / "arm_joint_contract.json").resolve()),
            "--pre-debug",
            str(debug_path.resolve()),
        ],
        check=True,
        timeout=120,
    )
    reopen_path = output / "reopen_debug.json"
    if not reopen_path.is_file():
        raise RuntimeError("saved-blend authority stage did not produce reopen_debug.json")
    write_authority_overlays(output)

    skeleton_entry = Path(__file__).resolve().with_name("blender_skeleton_viewport.py")
    command = [
        blender,
        str(blend_path.resolve()),
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

    skeleton_frames = [output / "skeleton_frames" / f"{frame:02d}.png" for frame in REVIEW_FRAMES]
    for path in skeleton_frames:
        if not path.is_file():
            raise RuntimeError(f"key-pose skeleton output missing: {path}")
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
        "authorityOverlay": "object_skeleton_overlay.png",
        "authorityOverlayFrames": "overlay_frames/",
        "debug": "motion_debug.json",
        "reopenDebug": "reopen_debug.json",
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
