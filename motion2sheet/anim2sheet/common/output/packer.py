from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image


def compose_sheet(frame_paths: list[Path], output: Path, *, columns: int) -> Path:
    if not frame_paths:
        raise ValueError("No animation frame PNGs supplied")
    if columns <= 0:
        raise ValueError("columns must be positive")
    images = [Image.open(path).convert("RGBA") for path in frame_paths]
    size = images[0].size
    if any(image.size != size for image in images):
        raise ValueError("All animation frames must have the same dimensions")
    rows = (len(images) + columns - 1) // columns
    sheet = Image.new("RGBA", (size[0] * columns, size[1] * rows), (0, 0, 0, 0))
    for index, image in enumerate(images):
        sheet.alpha_composite(image, ((index % columns) * size[0], (index // columns) * size[1]))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)
    for image in images:
        image.close()
    return output


def write_preview(frame_paths: list[Path], output: Path, *, fps: int) -> Path:
    if not frame_paths:
        raise ValueError("No animation frame PNGs supplied")
    if fps <= 0:
        raise ValueError("fps must be positive")
    images = [Image.open(path).convert("RGBA") for path in frame_paths]
    duration_ms = max(1, round(1000 / fps))
    output.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(
        output,
        save_all=True,
        append_images=images[1:],
        duration=duration_ms,
        loop=0,
        disposal=2,
        transparency=0,
    )
    for image in images:
        image.close()
    return output


def write_camera_previews(
    root: Path,
    camera_names: list[str],
    frames: list[int],
    *,
    fps: int,
    alias_camera: str,
    enabled: bool,
) -> list[Path]:
    """Package authoritative PNG frames into optional per-camera GIF previews.

    This is intentionally post-render packaging. It never invokes Blender and never
    mutates the source PNG frames used by authority verification.
    """
    if not enabled:
        return []
    if not camera_names:
        raise ValueError("No animation cameras supplied for GIF preview")
    if alias_camera not in camera_names:
        raise ValueError(f"GIF alias camera is not selected: {alias_camera}")

    outputs: list[Path] = []
    for camera_name in camera_names:
        camera_root = root / "cameras" / camera_name
        frame_paths = [camera_root / "frames" / f"{frame:02d}.png" for frame in frames]
        preview = write_preview(frame_paths, camera_root / "preview.gif", fps=fps)
        outputs.append(preview)

    alias_source = root / "cameras" / alias_camera / "preview.gif"
    top_level = root / "preview.gif"
    shutil.copy2(alias_source, top_level)
    outputs.append(top_level)
    return outputs
