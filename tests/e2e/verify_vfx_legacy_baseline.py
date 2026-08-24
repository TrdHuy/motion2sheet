from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from PIL import Image, ImageChops


RUN124_RGBA_SHA256 = {
    "01.png": "5832a3fd086b021f946cd0a24b52dfa40853fb7d10015c15c60bebb8aa3ea4f7",
    "02.png": "4b25a3356e4a92f606e888de08025790f9a1d2060b4678973a786d3604138c4d",
    "03.png": "f6387e146af3a99035e03c14e7a4864d158c344e5d8e0bf6d7f690d8c79b3939",
    "04.png": "feef5bf2958c0b04eddc875ab25f667221dc36fac1d844e7f8d76e08bcad64de",
    "05.png": "b38ef70091425e2fc6c23c72b2b3e10d896ad8a12a0d78e8574c680bdcb37186",
    "06.png": "ccea71cecebbb6c80782549d8cfd9729945d1a62967b8fba7e30ad20313ec0ca",
    "07.png": "02cbdb2ea58e141037599d1173055f7ba579ec4adbc5ef3635bf59d66e06b079",
    "08.png": "8c629da202ab0f9031d5d332f1bd52cf108dec8baed664da3bbf18d87685acd2",
}


def rgba_hash(path: Path) -> str:
    image = Image.open(path).convert("RGBA")
    return hashlib.sha256(image.tobytes()).hexdigest()


def verify_run124_hashes(output: Path) -> None:
    frame_dir = output / "frames"
    actual = sorted(path.name for path in frame_dir.glob("*.png"))
    expected = sorted(RUN124_RGBA_SHA256)
    if actual != expected:
        raise AssertionError(f"Unexpected baseline frame set: {actual}; expected {expected}")
    for name, expected_hash in RUN124_RGBA_SHA256.items():
        actual_hash = rgba_hash(frame_dir / name)
        if actual_hash != expected_hash:
            raise AssertionError(
                f"Dissolve-off regression in {name}: {actual_hash} != run124 {expected_hash}"
            )


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("legacy_output", type=Path)
    parser.add_argument("json5_off_output", type=Path)
    args = parser.parse_args()
    verify_run124_hashes(args.legacy_output)
    verify_run124_hashes(args.json5_off_output)
    verify_pixel_equal(args.legacy_output, args.json5_off_output)
    print("VFX legacy baseline: pixel-identical to run #124 and JSON5 dissolve-off")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
