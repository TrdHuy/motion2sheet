from __future__ import annotations

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
    images = [Image.open(path).convert("RGBA") for path in frame_paths]
    images[0].save(output, save_all=True, append_images=images[1:], duration=max(1, round(1000 / fps)), loop=0, disposal=2, transparency=0)
    for image in images:
        image.close()
    return output
