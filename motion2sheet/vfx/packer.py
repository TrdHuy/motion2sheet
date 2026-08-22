from __future__ import annotations

from pathlib import Path

from PIL import Image


def compose_sheet(frame_paths: list[Path], output: Path, *, columns: int) -> Path:
    if not frame_paths:
        raise ValueError("No VFX frame PNGs supplied")
    if columns <= 0:
        raise ValueError("columns must be positive")

    images = [Image.open(path).convert("RGBA") for path in frame_paths]
    frame_size = images[0].size
    if any(image.size != frame_size for image in images):
        raise ValueError("All VFX frames must have the same dimensions")

    rows = (len(images) + columns - 1) // columns
    sheet = Image.new("RGBA", (frame_size[0] * columns, frame_size[1] * rows), (0, 0, 0, 0))
    for index, image in enumerate(images):
        sheet.alpha_composite(
            image,
            ((index % columns) * frame_size[0], (index // columns) * frame_size[1]),
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)
    for image in images:
        image.close()
    return output


def write_preview(frame_paths: list[Path], output: Path, *, fps: int) -> Path:
    if not frame_paths:
        raise ValueError("No VFX frame PNGs supplied")
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
