"""Render one saved authoritative animation blend through configured cameras."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import bpy

from motion2sheet.anim2sheet.common.camera.blender import (
    apply_camera_config,
    project_named_points,
    projected_bones,
)

PROJECTED_POINTS = {
    "pelvis": ("Pelvis", "head"),
    "leftHip": ("LeftThigh", "head"),
    "leftKnee": ("LeftThigh", "tail"),
    "leftAnkle": ("LeftShin", "tail"),
    "rightHip": ("RightThigh", "head"),
    "rightKnee": ("RightThigh", "tail"),
    "rightAnkle": ("RightShin", "tail"),
    "leftShoulder": ("LeftUpperArm", "head"),
    "leftElbow": ("LeftUpperArm", "tail"),
    "leftWrist": ("LeftForeArm", "tail"),
    "rightShoulder": ("RightUpperArm", "head"),
    "rightElbow": ("RightUpperArm", "tail"),
    "rightWrist": ("RightForeArm", "tail"),
}
OVERLAY_BONES = [
    "Pelvis", "Spine", "Chest", "Neck", "Head",
    "LeftClavicle", "LeftUpperArm", "LeftForeArm", "LeftHand",
    "RightClavicle", "RightUpperArm", "RightForeArm", "RightHand",
    "LeftThigh", "LeftShin", "LeftFoot", "RightThigh", "RightShin", "RightFoot",
]


def argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def find_armature():
    values = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if len(values) != 1:
        raise RuntimeError(f"expected exactly one armature, got {len(values)}")
    return values[0]


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--camera-config", required=True)
    parser.add_argument("--output", required=True)
    args, _ = parser.parse_known_args(argv())
    config = json.loads(Path(args.camera_config).read_text(encoding="utf-8"))
    cameras = config["cameras"]
    names = config["selectedCameras"]
    review_frames = [int(value) for value in config.get("reviewFrames", [])]
    if not review_frames:
        raise RuntimeError("camera config missing reviewFrames")
    output = Path(args.output).resolve()
    scene = bpy.context.scene
    arm = find_armature()

    debug = {
        "sourceBlend": bpy.data.filepath,
        "selectedCameras": names,
        "reviewFrames": review_frames,
        "cameras": {},
    }
    for name in names:
        row = cameras[name]
        camera = apply_camera_config(scene, row)
        camera_root = output / "cameras" / name
        frame_dir = camera_root / "frames"
        frame_dir.mkdir(parents=True, exist_ok=True)
        frames = []
        for frame in review_frames:
            scene.frame_set(frame)
            bpy.context.view_layer.update()
            scene.render.filepath = str((frame_dir / f"{frame:02d}.png").resolve())
            bpy.ops.render.render(write_still=True)
            frames.append({
                "frame": frame,
                "projectedJoints": project_named_points(scene, camera, arm, PROJECTED_POINTS),
                "bonePixelSegments": projected_bones(scene, camera, arm, OVERLAY_BONES),
            })
        debug["cameras"][name] = {**row, "frames": frames}
    (output / "camera_debug.json").write_text(json.dumps(debug, indent=2) + "\n", encoding="utf-8")
    print(f"anim2sheet camera render OK: frames={review_frames}; cameras={names}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
