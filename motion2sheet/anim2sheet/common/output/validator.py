from __future__ import annotations

import json
from pathlib import Path
from PIL import Image, ImageChops, ImageStat


def validate_output(root: Path) -> list[str]:
    errors: list[str] = []
    required = ["source.json", "metadata.json", "source.blend", "motion_debug.json"]
    for name in required:
        path = root / name
        if not path.exists():
            errors.append(f"{name} is missing")
    if errors:
        return errors
    source = json.loads((root / "source.json").read_text(encoding="utf-8"))
    metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    debug = json.loads((root / "motion_debug.json").read_text(encoding="utf-8"))
    frames = int(source["frames"])
    canvas = tuple(source["canvas"])
    columns = int(source["sheetColumns"])
    frame_paths = sorted((root / "frames").glob("*.png"))
    if len(frame_paths) != frames:
        return errors + [f"expected {frames} frame PNGs, got {len(frame_paths)}"]
    changed = 0
    previous = None
    for path in frame_paths:
        with Image.open(path) as image:
            rgba = image.convert("RGBA")
            if rgba.size != canvas:
                errors.append(f"{path.name} has size {rgba.size}, expected {canvas}")
            alpha = rgba.getchannel("A")
            bbox = alpha.getbbox()
            if bbox is None:
                errors.append(f"{path.name} is fully transparent")
            else:
                if bbox[0] <= 1 or bbox[1] <= 1 or bbox[2] >= canvas[0] - 1 or bbox[3] >= canvas[1] - 1:
                    errors.append(f"{path.name} touches canvas edge")
            if previous is not None:
                diff = ImageChops.difference(previous, rgba)
                if max(ImageStat.Stat(diff).sum) > 1.0:
                    changed += 1
            previous = rgba.copy()
    if frames > 1 and changed < frames - 3:
        errors.append("animation is too static")
    sheet = root / "sprite_sheet.png"
    if not sheet.exists():
        errors.append("sprite_sheet.png is missing")
    else:
        rows = (frames + columns - 1) // columns
        with Image.open(sheet) as image:
            if image.size != (canvas[0] * columns, canvas[1] * rows):
                errors.append("sprite sheet dimensions do not match source contract")
            if image.mode != "RGBA":
                errors.append("sprite sheet must be RGBA")
    if not (root / "preview.gif").exists():
        errors.append("preview.gif is missing")
    if metadata.get("visualPipeline") != "blender-native":
        errors.append("metadata visualPipeline must be blender-native")
    if metadata.get("blendSource") != "source.blend":
        errors.append("metadata blendSource must reference source.blend")
    if metadata.get("postRenderVisualProcessing") is not False:
        errors.append("post-render visual processing must be disabled")
    samples = debug.get("samples", [])
    if len(samples) != frames:
        errors.append("motion_debug sample count does not match frames")
    return errors
