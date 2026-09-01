from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageEnhance

from .visual_contract import (
    COLUMNS,
    PANEL,
    ProjectionConfig,
    frame_numbers,
    panel_box,
    panel_origin,
    panel_pixel,
    projection_config,
    sheet_size,
)


def render_panel(frame: dict[str, Any], config: ProjectionConfig) -> Image.Image:
    image = Image.new("RGB", (PANEL, PANEL), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    origin = panel_pixel([0.0, 0.0, 0.0], config)
    draw.line((0, origin[1], PANEL - 1, origin[1]), fill=(225, 225, 225), width=1)
    for bone_name in sorted(frame):
        bone = frame[bone_name]
        head = panel_pixel(bone["head"], config)
        tail = panel_pixel(bone["tail"], config)
        draw.line((head, tail), fill=(20, 20, 20), width=2)
        radius = 2
        draw.ellipse((head[0] - radius, head[1] - radius, head[0] + radius, head[1] + radius), fill=(20, 20, 20))
    return image


def compose_sheet(images: list[Image.Image]) -> Image.Image:
    width, height = sheet_size(len(images))
    sheet = Image.new("RGB", (width, height), (255, 255, 255))
    for index, image in enumerate(images):
        sheet.paste(image, panel_origin(index))
    return sheet


def diff_metrics(first: Image.Image, second: Image.Image) -> tuple[int, int]:
    first = first.convert("RGB")
    second = second.convert("RGB")
    if first.size != second.size:
        raise ValueError(f"visual sheet size mismatch: {first.size} != {second.size}")
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


def _write_diff_outputs(source_sheet: Image.Image, reconstructed_sheet: Image.Image, output_dir: Path) -> tuple[int, int]:
    source_sheet = source_sheet.convert("RGB")
    reconstructed_sheet = reconstructed_sheet.convert("RGB")
    changed_pixels, max_delta = diff_metrics(source_sheet, reconstructed_sheet)
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
    amplified.save(output_dir / "diff_sheet.png")
    overlay.save(output_dir / "overlay_sheet.png")
    return changed_pixels, max_delta


def _frame_diff_summary(
    source_sheet: Image.Image,
    reconstructed_sheet: Image.Image,
    frames: tuple[int, ...],
) -> tuple[int | None, int]:
    worst_frame = None
    worst_changed = -1
    for index, frame in enumerate(frames):
        box = panel_box(index)
        changed, _delta = diff_metrics(source_sheet.crop(box), reconstructed_sheet.crop(box))
        if changed > worst_changed:
            worst_changed = changed
            worst_frame = frame
    return worst_frame, max(0, worst_changed)


def _visual_result(
    source_sheet: Image.Image,
    reconstructed_sheet: Image.Image,
    frames: tuple[int, ...],
    output_dir: Path,
    renderer: str,
) -> dict[str, Any]:
    expected_size = sheet_size(len(frames))
    if source_sheet.size != expected_size or reconstructed_sheet.size != expected_size:
        raise ValueError(
            f"visual sheet size must be {expected_size}; "
            f"source={source_sheet.size}, reconstructed={reconstructed_sheet.size}"
        )

    worst_frame, worst_changed = _frame_diff_summary(source_sheet, reconstructed_sheet, frames)
    total_changed, max_channel_delta = _write_diff_outputs(source_sheet, reconstructed_sheet, output_dir)
    return {
        "pass": total_changed == 0,
        "changedPixels": total_changed,
        "maxChannelDelta": max_channel_delta,
        "worstFrame": worst_frame,
        "worstFrameChangedPixels": worst_changed,
        "renderer": renderer,
        "frameCount": len(frames),
        "canvasPerFrame": [PANEL, PANEL],
        "columns": COLUMNS,
    }


def render_visuals(pose_data_path: Path, output_dir: Path) -> dict[str, Any]:
    """Render the legacy deterministic Pillow skeleton proof."""

    data = json.loads(pose_data_path.read_text(encoding="utf-8"))
    frames = frame_numbers(data)
    config = projection_config(data)
    source_sheet = compose_sheet([render_panel(data["source"][str(frame)], config) for frame in frames])
    reconstructed_sheet = compose_sheet(
        [render_panel(data["reconstructed"][str(frame)], config) for frame in frames]
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    source_sheet.save(output_dir / "source_sheet.png")
    reconstructed_sheet.save(output_dir / "reconstructed_sheet.png")
    return _visual_result(
        source_sheet,
        reconstructed_sheet,
        frames,
        output_dir,
        "deterministic-pillow-skeleton-v1",
    )


def compare_blender_rendered_visuals(pose_data_path: Path, output_dir: Path) -> dict[str, Any]:
    """Compare source/reconstructed sheets rendered natively by Blender.

    Blender owns source_sheet.png and reconstructed_sheet.png. Pillow owns only
    deterministic pixel comparison and diagnostic diff/overlay generation.
    """

    data = json.loads(pose_data_path.read_text(encoding="utf-8"))
    frames = frame_numbers(data)
    source_path = output_dir / "source_sheet.png"
    reconstructed_path = output_dir / "reconstructed_sheet.png"
    if not source_path.is_file() or not reconstructed_path.is_file():
        raise ValueError("Blender native renderer did not produce both visual sheets")

    with Image.open(source_path) as image:
        source_sheet = image.convert("RGB")
    with Image.open(reconstructed_path) as image:
        reconstructed_sheet = image.convert("RGB")

    return _visual_result(
        source_sheet,
        reconstructed_sheet,
        frames,
        output_dir,
        "blender-native-eevee-skeleton-v1",
    )
