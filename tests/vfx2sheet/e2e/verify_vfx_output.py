from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageChops


def load_rgba(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def verify_single(root: Path) -> None:
    source = json.loads((root / "source.json").read_text())
    frames = sorted((root / "frames").glob("*.png"))
    if len(frames) != source["frames"]:
        raise AssertionError(f"{root}: wrong frame count")

    areas = []
    widths = []
    centers = []
    for path in frames:
        with load_rgba(path) as image:
            alpha = image.getchannel("A")
            bbox = alpha.getbbox()
            if bbox is None:
                raise AssertionError(f"{root}/{path.name}: empty frame")
            areas.append(sum(1 for value in alpha.getdata() if value > 8))
            widths.append(bbox[2] - bbox[0])
            centers.append(((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0))

    peak_index = max(range(len(areas)), key=areas.__getitem__)
    if peak_index < 2 or peak_index > len(areas) - 2:
        raise AssertionError(f"{root}: peak frame is implausible: {peak_index + 1}")
    if areas[peak_index] <= areas[0] * 1.25:
        raise AssertionError(f"{root}: slash does not build up enough")
    if areas[-1] >= areas[peak_index] * 0.85:
        raise AssertionError(f"{root}: slash does not decay enough")
    if max(widths) < source["canvas"][0] * 0.25:
        raise AssertionError(f"{root}: slash silhouette is too narrow")

    for first, second in zip(centers, centers[1:]):
        if abs(first[0] - second[0]) > source["canvas"][0] * 0.25 or abs(first[1] - second[1]) > source["canvas"][1] * 0.25:
            raise AssertionError(f"{root}: effect centroid teleports between frames")


def compare_deterministic(a: Path, b: Path) -> None:
    for name in ("source.json", "metadata.json"):
        if (a / name).read_bytes() != (b / name).read_bytes():
            raise AssertionError(f"determinism failure: {name} differs")
    a_frames = sorted((a / "frames").glob("*.png"))
    b_frames = sorted((b / "frames").glob("*.png"))
    if len(a_frames) != len(b_frames):
        raise AssertionError("determinism failure: frame counts differ")
    for left, right in zip(a_frames, b_frames):
        with load_rgba(left) as image_a, load_rgba(right) as image_b:
            if ImageChops.difference(image_a, image_b).getbbox() is not None:
                raise AssertionError(f"determinism failure: {left.name} pixels differ")
    with load_rgba(a / "vfx_sheet.png") as sheet_a, load_rgba(b / "vfx_sheet.png") as sheet_b:
        if ImageChops.difference(sheet_a, sheet_b).getbbox() is not None:
            raise AssertionError("determinism failure: vfx_sheet.png pixels differ")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_a")
    parser.add_argument("run_b")
    args = parser.parse_args()
    a, b = Path(args.run_a), Path(args.run_b)
    verify_single(a)
    verify_single(b)
    compare_deterministic(a, b)
    print("VFX E2E semantics and determinism verified")


if __name__ == "__main__":
    main()
