from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image, ImageDraw

from ..output.packer import compose_sheet


def write_camera_overlays(output: Path, camera_debug: dict, camera_names: list[str], frames: list[int]) -> None:
    for name in camera_names:
        camera_root = output / "cameras" / name
        by_frame = {int(row["frame"]): row for row in camera_debug["cameras"][name]["frames"]}
        overlay_dir = camera_root / "overlay_frames"
        overlay_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for frame in frames:
            source_path = camera_root / "frames" / f"{frame:02d}.png"
            image = Image.open(source_path).convert("RGBA")
            draw = ImageDraw.Draw(image, "RGBA")
            for segment in by_frame[frame]["bonePixelSegments"]:
                head, tail = tuple(segment["headPx"]), tuple(segment["tailPx"])
                draw.line([head, tail], fill=(255, 40, 40, 235), width=4)
                for x, y in (head, tail):
                    r = 4
                    draw.ellipse([x-r, y-r, x+r, y+r], fill=(255, 230, 40, 245))
            path = overlay_dir / f"{frame:02d}.png"
            image.save(path)
            image.close()
            paths.append(path)
        compose_sheet(paths, camera_root / "object_skeleton_overlay.png", columns=4)


def copy_camera_aliases(output: Path, camera_name: str) -> None:
    source = output / "cameras" / camera_name
    for filename in ("object_keyposes.png", "skeleton_keyposes.png", "object_skeleton_overlay.png"):
        shutil.copy2(source / filename, output / filename)
    for src_name, dst_name in (("frames", "frames"), ("skeleton_frames", "skeleton_frames"), ("overlay_frames", "overlay_frames")):
        dst = output / dst_name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(source / src_name, dst)
