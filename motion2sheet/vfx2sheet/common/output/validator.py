from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat


def _alpha_bbox(image: Image.Image):
    return image.getchannel("A").getbbox()


def validate_output(root: Path) -> list[str]:
    errors: list[str] = []
    source_path = root / "source.json"
    metadata_path = root / "metadata.json"
    blend_path = root / "source.blend"
    if not source_path.exists():
        return ["source.json is missing"]
    if not metadata_path.exists():
        return ["metadata.json is missing"]
    if not blend_path.exists():
        errors.append("source.blend is missing")
    elif blend_path.stat().st_size < 1024:
        errors.append("source.blend is unexpectedly small")

    source = json.loads(source_path.read_text(encoding="utf-8"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    frames = int(source["frames"])
    canvas = tuple(source["canvas"])
    columns = int(source["sheetColumns"])
    frame_paths = sorted((root / "frames").glob("*.png"))
    if len(frame_paths) != frames:
        errors.append(f"expected {frames} frame PNGs, got {len(frame_paths)}")
        return errors

    alpha_areas: list[int] = []
    previous = None
    changed_pairs = 0
    for path in frame_paths:
        with Image.open(path) as image:
            rgba = image.convert("RGBA")
            if rgba.size != canvas:
                errors.append(f"{path.name} has size {rgba.size}, expected {canvas}")
            bbox = _alpha_bbox(rgba)
            if bbox is None:
                errors.append(f"{path.name} is fully transparent")
                continue
            alpha = rgba.getchannel("A")
            alpha_areas.append(sum(1 for value in alpha.getdata() if value > 8))
            corners = [
                alpha.getpixel((0, 0)),
                alpha.getpixel((canvas[0] - 1, 0)),
                alpha.getpixel((0, canvas[1] - 1)),
                alpha.getpixel((canvas[0] - 1, canvas[1] - 1)),
            ]
            if max(corners) > 4:
                errors.append(f"{path.name} touches a canvas corner")
            if previous is not None:
                diff = ImageChops.difference(previous, rgba)
                if max(ImageStat.Stat(diff).sum) > 1.0:
                    changed_pairs += 1
            previous = rgba.copy()

    if alpha_areas:
        if max(alpha_areas) < canvas[0] * canvas[1] * 0.005:
            errors.append("VFX alpha coverage is too small")
        if max(alpha_areas) <= min(alpha_areas) * 1.05:
            errors.append("VFX does not show meaningful buildup/decay")
    if frames > 1 and changed_pairs < frames - 2:
        errors.append("VFX animation is too static")

    sheet_path = root / "vfx_sheet.png"
    if not sheet_path.exists():
        errors.append("vfx_sheet.png is missing")
    else:
        rows = (frames + columns - 1) // columns
        with Image.open(sheet_path) as sheet:
            expected = (canvas[0] * columns, canvas[1] * rows)
            if sheet.size != expected:
                errors.append(f"sheet size {sheet.size}, expected {expected}")
            if sheet.mode != "RGBA":
                errors.append(f"sheet mode {sheet.mode}, expected RGBA")

    if not (root / "preview.gif").exists():
        errors.append("preview.gif is missing")
    if metadata.get("template") != source.get("template") or metadata.get("seed") != source.get("seed"):
        errors.append("metadata does not match source spec")
    if metadata.get("visualPipeline") != "blender-native":
        errors.append("metadata visualPipeline must be blender-native")
    if metadata.get("blendSource") != "source.blend":
        errors.append("metadata blendSource must reference source.blend")
    if metadata.get("postRenderVisualProcessing") is not False:
        errors.append("post-render visual processing must be disabled")
    return errors
