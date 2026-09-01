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

MIN_CELL_CONTENT_PIXELS = 16
CELL_FOREGROUND_CONTRAST = 48
MIN_BACKGROUND_LUMA = 128


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


def _cell_content_metrics(image: Image.Image) -> tuple[int, int, int]:
    """Return foreground pixels, dominant background luma and cutoff.

    Blender color management does not guarantee a literal white RGB background;
    the current Eevee proof commonly resolves the flat background around luma
    196-197. Estimate each cell's dominant background from its grayscale mode
    and count only pixels substantially darker than that background. A cropped
    blank cell therefore remains empty regardless of the renderer's background
    tone, while the dark skeleton remains strongly separated.
    """

    histogram = image.convert("L").histogram()
    background_luma = max(range(256), key=histogram.__getitem__)
    if background_luma < MIN_BACKGROUND_LUMA:
        return 0, background_luma, 0
    foreground_cutoff = max(0, background_luma - CELL_FOREGROUND_CONTRAST)
    content_pixels = sum(histogram[: foreground_cutoff + 1])
    return content_pixels, background_luma, foreground_cutoff


def sheet_layout_metrics(sheet: Image.Image, frames: tuple[int, ...]) -> dict[str, Any]:
    expected_size = sheet_size(len(frames))
    if sheet.size != expected_size:
        raise ValueError(f"visual sheet size must be {expected_size}; actual={sheet.size}")

    content_counts: list[int] = []
    background_lumas: list[int] = []
    foreground_cutoffs: list[int] = []
    empty_cells: list[dict[str, int]] = []
    for index, frame in enumerate(frames):
        content_pixels, background_luma, foreground_cutoff = _cell_content_metrics(sheet.crop(panel_box(index)))
        content_counts.append(content_pixels)
        background_lumas.append(background_luma)
        foreground_cutoffs.append(foreground_cutoff)
        if content_pixels < MIN_CELL_CONTENT_PIXELS:
            empty_cells.append({"index": index, "frame": frame})

    occupied = len(frames) - len(empty_cells)
    return {
        "pass": not empty_cells,
        "expectedCells": len(frames),
        "occupiedCells": occupied,
        "emptyCells": empty_cells,
        "minContentPixels": min(content_counts),
        "minBackgroundLuma": min(background_lumas),
        "maxForegroundCutoff": max(foreground_cutoffs),
        "foregroundContrast": CELL_FOREGROUND_CONTRAST,
        "minRequiredContentPixels": MIN_CELL_CONTENT_PIXELS,
    }


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

    source_layout = sheet_layout_metrics(source_sheet, frames)
    reconstructed_layout = sheet_layout_metrics(reconstructed_sheet, frames)
    layout_pass = source_layout["pass"] and reconstructed_layout["pass"]

    worst_frame, worst_changed = _frame_diff_summary(source_sheet, reconstructed_sheet, frames)
    total_changed, max_channel_delta = _write_diff_outputs(source_sheet, reconstructed_sheet, output_dir)
    return {
        "pass": total_changed == 0 and layout_pass,
        "changedPixels": total_changed,
        "maxChannelDelta": max_channel_delta,
        "worstFrame": worst_frame,
        "worstFrameChangedPixels": worst_changed,
        "renderer": renderer,
        "frameCount": len(frames),
        "canvasPerFrame": [PANEL, PANEL],
        "columns": COLUMNS,
        "rows": expected_size[1] // PANEL,
        "layout": {
            "pass": layout_pass,
            "source": source_layout,
            "reconstructed": reconstructed_layout,
        },
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
    deterministic pixel comparison, layout occupancy validation and diagnostic
    diff/overlay generation.
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
