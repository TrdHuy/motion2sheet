from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageChops


def verify_pixel_equal(first: Path, second: Path) -> None:
    first_frames = sorted((first / "frames").glob("*.png"))
    second_frames = sorted((second / "frames").glob("*.png"))
    if [p.name for p in first_frames] != [p.name for p in second_frames]:
        raise AssertionError("Legacy JSON and dissolve-off JSON5 frame sets differ")
    for first_path, second_path in zip(first_frames, second_frames):
        first_image = Image.open(first_path).convert("RGBA")
        second_image = Image.open(second_path).convert("RGBA")
        if first_image.size != second_image.size:
            raise AssertionError(f"Frame size mismatch: {first_path.name}")
        if ImageChops.difference(first_image, second_image).getbbox() is not None:
            raise AssertionError(f"Legacy JSON and dissolve-off JSON5 pixels differ: {first_path.name}")


def verify_blend_source(root: Path) -> None:
    path = root / "source.blend"
    if not path.exists() or path.stat().st_size < 1024:
        raise AssertionError(f"Missing usable Blender source: {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("legacy_output", type=Path)
    parser.add_argument("json5_off_output", type=Path)
    args = parser.parse_args()
    verify_pixel_equal(args.legacy_output, args.json5_off_output)
    verify_blend_source(args.legacy_output)
    verify_blend_source(args.json5_off_output)
    print("VFX compatibility: legacy JSON == JSON5 dissolve-off; both include editable source.blend")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
