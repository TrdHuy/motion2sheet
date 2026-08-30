"""Fast F1/F6/F7/F8 review with config-driven multi-camera rendering."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

import json5
from PIL import Image, ImageDraw

from .camera_profile import final_camera_name, load_camera_profile, resolve_camera_names
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


def write_camera_overlays(output: Path, camera_debug: dict, camera_names: list[str]) -> None:
    for name in camera_names:
        camera_root = output / "cameras" / name
        by_frame = {int(row["frame"]): row for row in camera_debug["cameras"][name]["frames"]}
        overlay_dir = camera_root / "overlay_frames"
        overlay_dir.mkdir(parents=True, exist_ok=True)
        overlay_paths = []
        for frame in REVIEW_FRAMES:
            source_path = camera_root / "frames" / f"{frame:02d}.png"
            image = Image.open(source_path).convert("RGBA")
            draw = ImageDraw.Draw(image, "RGBA")
            for segment in by_frame[frame]["bonePixelSegments"]:
                head = tuple(segment["headPx"]); tail = tuple(segment["tailPx"])
                draw.line([head, tail], fill=(255, 40, 40, 235), width=4)
                for point in (head, tail):
                    x, y = point; radius = 4
                    draw.ellipse([x-radius, y-radius, x+radius, y+radius], fill=(255, 230, 40, 245))
            path = overlay_dir / f"{frame:02d}.png"
            image.save(path); image.close(); overlay_paths.append(path)
        compose_sheet(overlay_paths, camera_root / "object_skeleton_overlay.png", columns=4)


def copy_final_aliases(output: Path, final_name: str) -> None:
    source = output / "cameras" / final_name
    for filename in ("object_keyposes.png", "skeleton_keyposes.png", "object_skeleton_overlay.png"):
        shutil.copy2(source / filename, output / filename)
    for src_dir_name, dst_dir_name in (
        ("frames", "frames"), ("skeleton_frames", "skeleton_frames"), ("overlay_frames", "overlay_frames")
    ):
        dst = output / dst_dir_name
        if dst.exists(): shutil.rmtree(dst)
        shutil.copytree(source / src_dir_name, dst)


def run(args) -> int:
    profile_path = Path(args.profile).resolve(); joint_path = Path(args.joint_contract).resolve()
    camera_profile_path = Path(args.camera_profile).resolve(); output = Path(args.output).resolve()
    if output.exists(): shutil.rmtree(output)
    output.mkdir(parents=True)

    camera_profile = load_camera_profile(camera_profile_path)
    camera_names = resolve_camera_names(camera_profile, args.cameras)
    final_name = final_camera_name(camera_profile, camera_names)
    if final_name is None:
        raise ValueError("fast keypose review requires one selected camera with role='final'")
    camera_config = {
        "version": camera_profile["version"],
        "source": camera_profile["source"],
        "selectedCameras": camera_names,
        "finalCamera": final_name,
        "cameras": {name: camera_profile["cameras"][name] for name in camera_names},
    }
    camera_config_path = output / "camera_config.json"
    camera_config_path.write_text(json.dumps(camera_config, indent=2) + "\n", encoding="utf-8")

    profile, ref_path, reference = load_profile(profile_path)
    source = dict(profile)
    source.update({
        "generator": "fast-keypose-deterministic-joint-fk-v2-multicamera",
        "reviewMode": "fast-keypose-review", "reviewFrames": REVIEW_FRAMES,
        "poseReferenceSource": str(ref_path), "poseReferenceData": reference,
        "armJointContractSource": str(joint_path), "cameraProfileSource": str(camera_profile_path),
    })
    source_path = output / "source.json"
    source_path.write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8")

    blender = blender_executable(args.blender)
    entry = Path(__file__).resolve().with_name("blender_keypose_entry.py")
    subprocess.run([blender, "--background", "--factory-startup", "--python", str(entry), "--",
                    "--spec", str(source_path), "--joint-contract", str(joint_path), "--output", str(output)],
                   check=True, timeout=240)
    blend_path = output / "source.blend"; debug_path = output / "motion_debug.json"
    if not blend_path.is_file() or not debug_path.is_file():
        raise RuntimeError("authoring stage did not produce source.blend/motion_debug.json")

    # Inspect the exact saved pose before any camera-specific work. This is a
    # representation diagnostic only: it records leg rest axes, IK pole angle,
    # authored guide bend direction and evaluated knee bend direction.
    leg_debug_entry = Path(__file__).resolve().with_name("blender_leg_ik_debug.py")
    subprocess.run([blender, "--background", str(blend_path), "--python", str(leg_debug_entry), "--",
                    "--output", str(output), "--frames", ",".join(str(v) for v in REVIEW_FRAMES)],
                   check=True, timeout=120)
    if not (output / "leg_ik_debug.json").is_file():
        raise RuntimeError("leg_ik_debug.json missing")

    # Reopen exactly the same saved blend and change camera only.
    camera_entry = Path(__file__).resolve().with_name("blender_camera_render.py")
    subprocess.run([blender, "--background", str(blend_path), "--python", str(camera_entry), "--",
                    "--camera-config", str(camera_config_path), "--output", str(output)],
                   check=True, timeout=240)
    camera_debug_path = output / "camera_debug.json"
    if not camera_debug_path.is_file(): raise RuntimeError("camera_debug.json missing")
    camera_debug = json.loads(camera_debug_path.read_text(encoding="utf-8"))

    reopen_entry = Path(__file__).resolve().with_name("blender_reopen_verify.py")
    subprocess.run([blender, "--background", str(blend_path), "--python", str(reopen_entry), "--",
                    "--output", str(output), "--contract", str(output / "arm_joint_contract.json"),
                    "--pre-debug", str(debug_path)], check=True, timeout=120)
    if not (output / "reopen_debug.json").is_file(): raise RuntimeError("reopen_debug.json missing")

    skeleton_entry = Path(__file__).resolve().with_name("blender_skeleton_viewport.py")
    xvfb = shutil.which("xvfb-run")
    for name in camera_names:
        camera_root = output / "cameras" / name
        object_frames = [camera_root / "frames" / f"{frame:02d}.png" for frame in REVIEW_FRAMES]
        for path in object_frames:
            if not path.is_file(): raise RuntimeError(f"camera object output missing: {path}")
        compose_sheet(object_frames, camera_root / "object_keyposes.png", columns=4)

        command = [blender, str(blend_path), "--python", str(skeleton_entry), "--",
                   "--output", str(camera_root / "skeleton_frames"), "--rig-output", str(output),
                   "--frames", ",".join(str(v) for v in REVIEW_FRAMES), "--skip-rig-docs",
                   "--camera-config", str(camera_config_path), "--camera-name", name]
        if xvfb: command = [xvfb, "-a", *command]
        subprocess.run(command, check=True, timeout=120)
        skeleton_frames = [camera_root / "skeleton_frames" / f"{frame:02d}.png" for frame in REVIEW_FRAMES]
        for path in skeleton_frames:
            if not path.is_file(): raise RuntimeError(f"camera skeleton output missing: {path}")
        compose_sheet(skeleton_frames, camera_root / "skeleton_keyposes.png", columns=4)

    write_camera_overlays(output, camera_debug, camera_names)
    copy_final_aliases(output, final_name)

    metadata = {
        "tool": "anim2sheet", "mode": "fast-keypose-review", "reviewFrames": REVIEW_FRAMES,
        "armControl": "deterministic_joint_fk", "legControl": "ik_with_explicit_knee_poles",
        "torsoControl": "fk_with_fast_body_overrides", "weaponBinding": "two_hand_joint_grip",
        "cameraProfile": str(camera_profile_path), "reviewCameras": camera_names, "finalCamera": final_name,
        "cameraRoot": "cameras/", "cameraDebug": "camera_debug.json", "legIkDebug": "leg_ik_debug.json",
        "objectPreview": "object_keyposes.png", "skeletonPreview": "skeleton_keyposes.png",
        "authorityOverlay": "object_skeleton_overlay.png", "authorityOverlayFrames": "overlay_frames/",
        "debug": "motion_debug.json", "reopenDebug": "reopen_debug.json", "sourceBlend": "source.blend",
    }
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"anim2sheet multi-camera fast key-pose review OK -> {output}; cameras={camera_names}", flush=True)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--joint-contract", required=True)
    parser.add_argument("--camera-profile", required=True)
    parser.add_argument("--cameras", default=None)
    parser.add_argument("--output", required=True)
    parser.add_argument("--blender", default="blender")
    args = parser.parse_args(argv)
    try: return run(args)
    except (RuntimeError, subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, ValueError) as exc:
        print(f"anim2sheet keypose review: {exc}", flush=True); return 2


if __name__ == "__main__": raise SystemExit(main())
