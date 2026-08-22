from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageOps


def split_sheet(image: Image.Image, columns: int = 4, rows: int = 2) -> list[Image.Image]:
    width, height = image.size
    if width % columns or height % rows:
        raise AssertionError(f"sheet {image.size} is not divisible by {columns}x{rows}")
    cell_w, cell_h = width // columns, height // rows
    return [
        image.crop((column * cell_w, row * cell_h, (column + 1) * cell_w, (row + 1) * cell_h)).convert("RGBA")
        for row in range(rows)
        for column in range(columns)
    ]


def alpha_area(frame: Image.Image) -> int:
    return sum(1 for value in frame.getchannel("A").getdata() if value > 8)


def color_fractions(frame: Image.Image) -> dict[str, float]:
    rgba = frame.convert("RGBA")
    pixels = [pixel for pixel in rgba.getdata() if pixel[3] > 8]
    if not pixels:
        return {"white": 0.0, "cyan": 0.0, "blue": 0.0}
    count = len(pixels)
    white = sum(1 for r, g, b, _ in pixels if r > 210 and g > 225 and b > 225) / count
    cyan = sum(1 for r, g, b, _ in pixels if g > 125 and b > 160 and b >= r * 1.15) / count
    blue = sum(1 for r, g, b, _ in pixels if b > 105 and b >= r * 1.30) / count
    return {"white": white, "cyan": cyan, "blue": blue}


def normalized_mask(frame: Image.Image, size: int = 96) -> Image.Image:
    alpha = frame.getchannel("A").point(lambda value: 255 if value > 8 else 0)
    bbox = alpha.getbbox()
    if bbox is None:
        return Image.new("1", (size, size), 0)
    crop = alpha.crop(bbox)
    target = size - 12
    scale = min(target / crop.width, target / crop.height)
    resized = crop.resize((max(1, round(crop.width * scale)), max(1, round(crop.height * scale))), Image.Resampling.NEAREST)
    canvas = Image.new("L", (size, size), 0)
    canvas.paste(resized, ((size - resized.width) // 2, (size - resized.height) // 2))
    return canvas.point(lambda value: 255 if value > 0 else 0).convert("1")


def mask_iou(left: Image.Image, right: Image.Image) -> float:
    left_data = list(left.getdata())
    right_data = list(right.getdata())
    intersection = sum(1 for a, b in zip(left_data, right_data) if a and b)
    union = sum(1 for a, b in zip(left_data, right_data) if a or b)
    return intersection / union if union else 1.0


def roughness(frame: Image.Image) -> float:
    mask = normalized_mask(frame, 96)
    data = list(mask.getdata())
    width, height = mask.size
    area = sum(1 for value in data if value)
    if not area:
        return 0.0
    boundary = 0
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            index = y * width + x
            if not data[index]:
                continue
            if not (data[index - 1] and data[index + 1] and data[index - width] and data[index + width]):
                boundary += 1
    return boundary / math.sqrt(area)


def frame_metrics(frames: list[Image.Image]) -> list[dict[str, float | int]]:
    metrics = []
    for frame in frames:
        colors = color_fractions(frame)
        metrics.append({
            "area": alpha_area(frame),
            "white": colors["white"],
            "cyan": colors["cyan"],
            "blue": colors["blue"],
            "roughness": roughness(frame),
        })
    return metrics


def write_overlay(reference: Image.Image, output: Image.Image, path: Path) -> None:
    width = max(reference.width, output.width)
    ref_scaled = ImageOps.contain(reference, (width, max(1, round(reference.height * width / reference.width))))
    out_scaled = ImageOps.contain(output, (width, max(1, round(output.height * width / output.width))))
    canvas = Image.new("RGBA", (width, ref_scaled.height + out_scaled.height), (0, 0, 0, 0))
    canvas.paste(ref_scaled, ((width - ref_scaled.width) // 2, 0), ref_scaled)
    canvas.paste(out_scaled, ((width - out_scaled.width) // 2, ref_scaled.height), out_scaled)
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path)


def verify(reference_path: Path, output_root: Path, qa_root: Path) -> None:
    reference_sheet = Image.open(reference_path).convert("RGBA")
    output_sheet = Image.open(output_root / "vfx_sheet.png").convert("RGBA")
    reference_frames = split_sheet(reference_sheet)
    output_frames = split_sheet(output_sheet)
    if len(reference_frames) != len(output_frames):
        raise AssertionError("golden reference and output frame counts differ")

    ref_metrics = frame_metrics(reference_frames)
    out_metrics = frame_metrics(output_frames)
    ref_areas = [int(item["area"]) for item in ref_metrics]
    out_areas = [int(item["area"]) for item in out_metrics]
    ref_peak = max(range(len(ref_areas)), key=ref_areas.__getitem__)
    out_peak = max(range(len(out_areas)), key=out_areas.__getitem__)
    if abs(ref_peak - out_peak) > 1:
        raise AssertionError(f"peak timing differs too much: reference={ref_peak + 1}, output={out_peak + 1}")
    if out_areas[out_peak] <= out_areas[0] * 1.65:
        raise AssertionError("output lacks reference-like buildup")
    if out_areas[-1] >= out_areas[out_peak] * 0.58:
        raise AssertionError("output lacks reference-like breakup/decay")

    peak_colors = out_metrics[out_peak]
    if float(peak_colors["white"]) < 0.025:
        raise AssertionError("peak frame lacks a white-hot core")
    if float(peak_colors["cyan"]) < 0.10:
        raise AssertionError("peak frame lacks a cyan inner-energy layer")
    if float(peak_colors["blue"]) < 0.45:
        raise AssertionError("peak frame lacks a dominant blue outer body")

    ious = [mask_iou(normalized_mask(ref), normalized_mask(out)) for ref, out in zip(reference_frames, output_frames)]
    peak_iou = ious[out_peak]
    mean_iou = sum(ious) / len(ious)
    if peak_iou < 0.16 or mean_iou < 0.12:
        raise AssertionError(f"crescent silhouette is too far from golden direction: peak IoU={peak_iou:.3f}, mean IoU={mean_iou:.3f}")

    # The approved reference becomes visibly rougher as it breaks apart. Require the same direction.
    if float(out_metrics[-1]["roughness"]) <= float(out_metrics[out_peak]["roughness"]) * 1.02:
        raise AssertionError("decay frame is not visibly more fragmented than the peak")

    report = {
        "reference": str(reference_path),
        "output": str(output_root / "vfx_sheet.png"),
        "referencePeakFrame": ref_peak + 1,
        "outputPeakFrame": out_peak + 1,
        "frameIoU": [round(value, 4) for value in ious],
        "meanIoU": round(mean_iou, 4),
        "peakIoU": round(peak_iou, 4),
        "referenceMetrics": ref_metrics,
        "outputMetrics": out_metrics,
    }
    qa_root.mkdir(parents=True, exist_ok=True)
    (qa_root / "comparison_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_overlay(reference_sheet, output_sheet, qa_root / "comparison_overlay.png")
    print(f"VFX golden-reference QA verified: peak IoU={peak_iou:.3f}, mean IoU={mean_iou:.3f}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--qa-output", required=True)
    args = parser.parse_args()
    verify(Path(args.reference), Path(args.output), Path(args.qa_output))


if __name__ == "__main__":
    main()
