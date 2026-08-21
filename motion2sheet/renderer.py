from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from .model import BONES, PoseFrame, PoseSequence

BONE_COLORS = (
    (255, 80, 80, 255),
    (255, 180, 60, 255),
    (245, 240, 80, 255),
    (80, 220, 100, 255),
    (70, 210, 220, 255),
    (80, 130, 255, 255),
    (190, 90, 255, 255),
    (255, 90, 190, 255),
)


def render_frame(
    frame: PoseFrame,
    canvas: tuple[int, int],
    *,
    background: tuple[int, int, int, int] = (0, 0, 0, 255),
    line_width: int = 5,
    joint_radius: int = 5,
) -> Image.Image:
    image = Image.new("RGBA", canvas, background)
    draw = ImageDraw.Draw(image)

    for index, (start, end) in enumerate(BONES):
        if start not in frame.joints or end not in frame.joints:
            continue
        draw.line(
            [frame.joints[start], frame.joints[end]],
            fill=BONE_COLORS[index % len(BONE_COLORS)],
            width=line_width,
        )

    for x, y in frame.joints.values():
        draw.ellipse(
            (x - joint_radius, y - joint_radius, x + joint_radius, y + joint_radius),
            fill=(255, 255, 255, 255),
        )
    return image


def render_sequence(sequence: PoseSequence, frames_dir: Path) -> list[Path]:
    frames_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index, frame in enumerate(sequence.frames, start=1):
        path = frames_dir / f"{index:02d}.png"
        render_frame(frame, sequence.canvas).save(path)
        paths.append(path)
    return paths


def compose_sheet(frame_paths: list[Path], output: Path, columns: int = 4) -> Path:
    if not frame_paths:
        raise ValueError("No frame PNGs supplied")
    images = [Image.open(path).convert("RGBA") for path in frame_paths]
    frame_w, frame_h = images[0].size
    if any(image.size != (frame_w, frame_h) for image in images):
        raise ValueError("All frame PNGs must have the same size")

    rows = (len(images) + columns - 1) // columns
    sheet = Image.new("RGBA", (frame_w * columns, frame_h * rows), (0, 0, 0, 255))
    for index, image in enumerate(images):
        x = (index % columns) * frame_w
        y = (index // columns) * frame_h
        sheet.alpha_composite(image, (x, y))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)
    return output
