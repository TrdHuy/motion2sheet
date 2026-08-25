from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from PIL import Image, ImageChops


def rgba_hash(path: Path) -> str:
    with Image.open(path) as image:
        return hashlib.sha256(image.convert("RGBA").tobytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("original_root", type=Path)
    parser.add_argument("reopened_frames", type=Path)
    args = parser.parse_args()

    original = sorted((args.original_root / "frames").glob("*.png"))
    reopened = sorted(args.reopened_frames.glob("*.png"))
    if [p.name for p in original] != [p.name for p in reopened]:
        raise AssertionError("saved .blend re-render frame set differs from CLI output")
    for expected, actual in zip(original, reopened):
        if rgba_hash(expected) != rgba_hash(actual):
            with Image.open(expected) as a, Image.open(actual) as b:
                if ImageChops.difference(a.convert("RGBA"), b.convert("RGBA")).getbbox() is not None:
                    raise AssertionError(f"saved .blend does not reproduce {expected.name}")
    print("saved source.blend re-renders all frames pixel-identically")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
