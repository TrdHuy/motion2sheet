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
    if [path.name for path in first_frames] != [path.name for path in second_frames]:
        raise AssertionError("3D trajectory deterministic frame sets differ")
    for a, b in zip(first_frames, second_frames):
        if ImageChops.difference(Image.open(a).convert("RGBA"), Image.open(b).convert("RGBA")).getbbox() is not None:
            raise AssertionError(f"3D trajectory is not deterministic: {a.name}")


def _assert_contract(root: Path) -> None:
    source = json.loads((root / "source.json").read_text(encoding="utf-8"))
    trajectory = source.get("trajectory") or {}
    if trajectory.get("type") != "conical-helix":
        raise AssertionError("source.json does not preserve conical-helix trajectory")
    if trajectory.get("dimensions") != 3:
        raise AssertionError("conical helix trajectory is not canonical 3D")
    if not (float(trajectory.get("radiusStart", 0)) > float(trajectory.get("radiusEnd", 0)) >= 0):
        raise AssertionError("conical helix does not taper from large to small")
    if not (float(trajectory.get("top", 0)) > float(trajectory.get("bottom", 0))):
        raise AssertionError("conical helix does not rise from bottom to top")

    metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    if metadata.get("trajectoryProvider") != "conical-helix":
        raise AssertionError("metadata does not identify conical helix provider")
    if metadata.get("trajectoryDimensions") != 3:
        raise AssertionError("metadata does not identify 3D trajectory")
    if metadata.get("visualPipeline") != "blender-native" or metadata.get("postRenderVisualProcessing") is not False:
        raise AssertionError("3D trajectory build stopped being Blender-native")
    blend = root / "source.blend"
    if not blend.exists() or blend.stat().st_size < 1024:
        raise AssertionError("3D trajectory build is missing usable source.blend")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_a", type=Path)
    parser.add_argument("run_b", type=Path)
    args = parser.parse_args()
    _assert_contract(args.run_a)
    _assert_contract(args.run_b)
    _assert_pixel_equal(args.run_a, args.run_b)
    print("VFX 3D trajectory: conical helix preserved, Blender-rendered, and deterministic")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
