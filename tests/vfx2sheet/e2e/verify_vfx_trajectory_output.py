from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageChops


def _frames(root: Path) -> list[Path]:
    paths = sorted((root / "frames").glob("*.png"))
    if not paths:
        raise AssertionError(f"No rendered frames: {root}")
    return paths


def _assert_pixel_equal(first: Path, second: Path) -> None:
    first_frames, second_frames = _frames(first), _frames(second)
    if [p.name for p in first_frames] != [p.name for p in second_frames]:
        raise AssertionError("Point trajectory deterministic frame sets differ")
    for a, b in zip(first_frames, second_frames):
        if ImageChops.difference(Image.open(a).convert("RGBA"), Image.open(b).convert("RGBA")).getbbox() is not None:
            raise AssertionError(f"Point trajectory is not deterministic: {a.name}")


def _assert_changes_default(default: Path, points: Path) -> None:
    default_frames, point_frames = _frames(default), _frames(points)
    if len(default_frames) != len(point_frames):
        raise AssertionError("Default and point trajectory frame counts differ")
    changed = 0
    for a, b in zip(default_frames, point_frames):
        if ImageChops.difference(Image.open(a).convert("RGBA"), Image.open(b).convert("RGBA")).getbbox() is not None:
            changed += 1
    if changed < max(1, len(point_frames) // 2):
        raise AssertionError(f"Point trajectory affected too few frames: {changed}/{len(point_frames)}")


def _assert_contract(root: Path) -> None:
    source = json.loads((root / "source.json").read_text(encoding="utf-8"))
    trajectory = source.get("trajectory")
    if not trajectory or trajectory.get("type") != "points":
        raise AssertionError("source.json does not preserve the point trajectory")
    if trajectory.get("interpolation") != "catmull-rom" or trajectory.get("closed") is not False:
        raise AssertionError("source.json trajectory contract is not canonical")
    if len(trajectory.get("points", [])) < 2:
        raise AssertionError("source.json trajectory points missing")

    metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    if metadata.get("trajectoryProvider") != "points":
        raise AssertionError("metadata does not identify point trajectory provider")
    if metadata.get("visualPipeline") != "blender-native":
        raise AssertionError("trajectory build stopped being Blender-native")
    if metadata.get("postRenderVisualProcessing") is not False:
        raise AssertionError("trajectory build unexpectedly uses post-render visual processing")

    blend = root / "source.blend"
    if not blend.exists() or blend.stat().st_size < 1024:
        raise AssertionError("Point trajectory build is missing usable source.blend")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("default_output", type=Path)
    parser.add_argument("point_run_a", type=Path)
    parser.add_argument("point_run_b", type=Path)
    args = parser.parse_args()

    _assert_contract(args.point_run_a)
    _assert_contract(args.point_run_b)
    _assert_pixel_equal(args.point_run_a, args.point_run_b)
    _assert_changes_default(args.default_output, args.point_run_a)
    print("VFX trajectory: point config preserved, Blender-rendered, deterministic, and visually active")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
