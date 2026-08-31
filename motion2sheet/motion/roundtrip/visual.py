from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageEnhance

PANEL = 256
PADDING = 18
COLUMNS = 8


def _project(point: list[float]) -> tuple[float, float]:
    x, y, z = (float(value) for value in point)
    return x - 0.42 * y, z + 0.20 * y


def _frame_points(frame: dict[str, Any]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for bone in frame.values():
        points.append(_project(bone["head"]))
        points.append(_project(bone["tail"]))
    return points


def _projection_config(data: dict[str, Any]) -> dict[str, float]:
    points: list[tuple[float, float]] = []
    for branch in ("source", "reconstructed"):
        for frame in data[branch].values():
            points.extend(_frame_points(frame))
    if not points:
        raise ValueError("visual pose data has no points")
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = max(max_x - min_x, 1e-9)
    height = max(max_y - min_y, 1e-9)
    scale = min((PANEL - 2 * PADDING) / width, (PANEL - 2 * PADDING) / height)
    return {"minX": min_x, "minY": min_y, "maxY": max_y, "scale": scale}


def _pixel(point: list[float], config: dict[str, float]) -> tuple[int, int]:
    x, y = _project(point)
    px = PADDING + (x - config["minX"]) * config["scale"]
    py = PADDING + (config["maxY"] - y) * config["scale"]
    return int(round(px)), int(round(py))


def render_panel(frame: dict[str, Any], config: dict[str, float]) -> Image.Image:
    image = Image.new("RGB", (PANEL, PANEL), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    origin = _pixel([0.0, 0.0, 0.0], config)
    draw.line((0, origin[1], PANEL - 1, origin[1]), fill=(225, 225, 225), width=1)
    for bone_name in sorted(frame):
        bone = frame[bone_name]
        head = _pixel(bone["head"], config)
        tail = _pixel(bone["tail"], config)
        draw.line((head, tail), fill=(20, 20, 20), width=2)
        radius = 2
        draw.ellipse((head[0] - radius, head[1] - radius, head[0] + radius, head[1] + radius), fill=(20, 20, 20))
    return image


def compose_sheet(images: list[Image.Image]) -> Image.Image:
    if not images:
        raise ValueError("cannot compose an empty visual sheet")
    rows = math.ceil(len(images) / COLUMNS)
    sheet = Image.new("RGB", (PANEL * COLUMNS, PANEL * rows), (255, 255, 255))
    for index, image in enumerate(images):
        x = (index % COLUMNS) * PANEL
        y = (index // COLUMNS) * PANEL
        sheet.paste(image, (x, y))
    return sheet


def diff_metrics(first: Image.Image, second: Image.Image) -> tuple[int, int]:
    first_bytes = first.tobytes()
    second_bytes = second.tobytes()
    changed_pixels = 0
    max_delta = 0
    for offset in range(0, len(first_bytes), 3):
        deltas = [abs(first_bytes[offset + channel] - second_bytes[offset + channel]) for channel in range(3)]
        if any(deltas):
            changed_pixels += 1
            max_delta = max(max_delta, *deltas)
    return changed_pixels, max_delta


def render_visuals(pose_data_path: Path, output_dir: Path) -> dict[str, Any]:
    data = json.loads(pose_data_path.read_text(encoding="utf-8"))
    start, end = data["frameRange"]
    frames = list(range(int(start), int(end) + 1))
    config = _projection_config(data)
    source_panels: list[Image.Image] = []
    reconstructed_panels: list[Image.Image] = []
    worst_frame = None
    worst_changed = -1
    total_changed = 0
    max_channel_delta = 0
    for frame in frames:
        source = render_panel(data["source"][str(frame)], config)
        reconstructed = render_panel(data["reconstructed"][str(frame)], config)
        source_panels.append(source)
        reconstructed_panels.append(reconstructed)
        changed, delta = diff_metrics(source, reconstructed)
        total_changed += changed
        max_channel_delta = max(max_channel_delta, delta)
        if changed > worst_changed:
            worst_changed = changed
            worst_frame = frame
    source_sheet = compose_sheet(source_panels)
    reconstructed_sheet = compose_sheet(reconstructed_panels)
    difference = ImageChops.difference(source_sheet, reconstructed_sheet)
    amplified = ImageEnhance.Contrast(difference).enhance(8.0)
    source_gray = source_sheet.convert("L")
    reconstructed_gray = reconstructed_sheet.convert("L")
    overlay = Image.merge(
        "RGB",
        (
            source_gray,
            reconstructed_gray,
            ImageChops.blend(source_gray, reconstructed_gray, 0.5),
        ),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    source_sheet.save(output_dir / "source_sheet.png")
    reconstructed_sheet.save(output_dir / "reconstructed_sheet.png")
    amplified.save(output_dir / "diff_sheet.png")
    overlay.save(output_dir / "overlay_sheet.png")
    return {
        "pass": total_changed == 0,
        "changedPixels": total_changed,
        "maxChannelDelta": max_channel_delta,
        "worstFrame": worst_frame,
        "worstFrameChangedPixels": max(0, worst_changed),
        "renderer": "deterministic-pillow-skeleton-v1",
        "frameCount": len(frames),
        "canvasPerFrame": [PANEL, PANEL],
        "columns": COLUMNS,
    }
