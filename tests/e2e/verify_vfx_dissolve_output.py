from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw


def rgba(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def active_pixels(image: Image.Image, threshold: int = 24) -> set[tuple[int, int]]:
    alpha = image.getchannel("A")
    return {(x, y) for y in range(image.height) for x in range(image.width) if alpha.getpixel((x, y)) > threshold}


def component_count(image: Image.Image, threshold: int = 54, minimum_size: int = 5) -> int:
    points = active_pixels(image, threshold)
    count = 0
    while points:
        start = points.pop()
        queue = deque([start])
        size = 1
        while queue:
            x, y = queue.popleft()
            for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if neighbor in points:
                    points.remove(neighbor)
                    queue.append(neighbor)
                    size += 1
        if size >= minimum_size:
            count += 1
    return count


def build_comparison(baseline: Path, dissolved: Path, output: Path) -> None:
    frames = []
    for frame_number in (6, 7, 8):
        base = rgba(baseline / "frames" / f"{frame_number:02d}.png")
        active = rgba(dissolved / "frames" / f"{frame_number:02d}.png")
        canvas = Image.new("RGBA", (base.width * 2, base.height), (8, 8, 12, 255))
        canvas.alpha_composite(base, (0, 0))
        canvas.alpha_composite(active, (base.width, 0))
        draw = ImageDraw.Draw(canvas)
        draw.text((10, 10), f"F{frame_number} baseline", fill=(255, 255, 255, 255))
        draw.text((base.width + 10, 10), f"F{frame_number} dissolve", fill=(255, 255, 255, 255))
        frames.append(canvas)
    sheet = Image.new("RGBA", (frames[0].width, sum(frame.height for frame in frames)), (8, 8, 12, 255))
    y = 0
    for frame in frames:
        sheet.alpha_composite(frame, (0, y))
        y += frame.height
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline")
    parser.add_argument("run_a")
    parser.add_argument("run_b")
    parser.add_argument("--qa-output", required=True)
    args = parser.parse_args()
    baseline = Path(args.baseline)
    run_a = Path(args.run_a)
    run_b = Path(args.run_b)

    # Cùng JSON5 + seed phải cho cùng pixel ở mọi frame.
    for frame_number in range(1, 9):
        a = rgba(run_a / "frames" / f"{frame_number:02d}.png")
        b = rgba(run_b / "frames" / f"{frame_number:02d}.png")
        if a.tobytes() != b.tobytes():
            raise SystemExit(f"dissolve determinism failed at F{frame_number}")

    # Với start=0.62, F1-F5 phải pixel-identical với baseline strength=0.
    for frame_number in range(1, 6):
        base = rgba(baseline / "frames" / f"{frame_number:02d}.png")
        active = rgba(run_a / "frames" / f"{frame_number:02d}.png")
        if base.tobytes() != active.tobytes():
            raise SystemExit(f"dissolve changed pre-start frame F{frame_number}")

    base7 = rgba(baseline / "frames" / "07.png")
    base8 = rgba(baseline / "frames" / "08.png")
    active7 = rgba(run_a / "frames" / "07.png")
    active8 = rgba(run_a / "frames" / "08.png")
    base7_area, active7_area = len(active_pixels(base7)), len(active_pixels(active7))
    base8_area, active8_area = len(active_pixels(base8)), len(active_pixels(active8))
    if active7_area >= base7_area * 0.96:
        raise SystemExit(f"F7 dissolve breakup too weak: baseline={base7_area} active={active7_area}")
    if active8_area >= base8_area * 0.90:
        raise SystemExit(f"F8 dissolve breakup too weak: baseline={base8_area} active={active8_area}")

    base_components = component_count(base8)
    active_components = component_count(active8)
    if active_components <= base_components:
        raise SystemExit(f"F8 dissolve did not increase fragmentation: baseline={base_components} active={active_components}")

    qa = Path(args.qa_output)
    build_comparison(baseline, run_a, qa / "baseline_vs_dissolve_f6_f8.png")
    (qa / "metrics.txt").write_text(
        f"F7 active area: {active7_area}/{base7_area}\n"
        f"F8 active area: {active8_area}/{base8_area}\n"
        f"F8 components: {active_components}/{base_components}\n",
        encoding="utf-8",
    )
    print("dissolve semantics OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
