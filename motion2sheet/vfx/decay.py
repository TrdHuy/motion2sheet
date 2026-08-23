from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw


def _hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def _add_decay_shards(
    frame: Image.Image,
    params: dict[str, str | float | int],
    *,
    seed: int,
    frame_index: int,
    frame_count: int,
) -> Image.Image:
    if frame_count < 2 or frame_index < frame_count - 2:
        return frame
    alpha = frame.getchannel("A")
    active = [(x, y) for y in range(frame.height) for x in range(frame.width) if alpha.getpixel((x, y)) > 110]
    if not active:
        return frame
    xs = [point[0] for point in active]
    ys = [point[1] for point in active]
    cx = (min(xs) + max(xs)) * 0.5
    cy = (min(ys) + max(ys)) * 0.5
    decay_stage = (frame_index - (frame_count - 2) + 1) / 2.0
    rng = random.Random(seed * 1009 + frame_index * 9176 + 73)
    requested = int(params["fragments.count"])
    count = min(28, max(8, round(requested * (0.22 + 0.15 * decay_stage))))
    spread = float(params["fragments.spread"])
    size = float(params["fragments.size"])
    blue = (*_hex_rgb(str(params["colors.body"])), 225)
    cyan = (*_hex_rgb(str(params["colors.inner"])), 235)
    white = (*_hex_rgb(str(params["colors.lightning"])), 238)
    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    shard_tips: list[tuple[float, float, float, float]] = []
    for index in range(count):
        ax, ay = active[rng.randrange(len(active))]
        vx, vy = ax - cx, ay - cy
        magnitude = math.hypot(vx, vy) or 1.0
        vx, vy = vx / magnitude, vy / magnitude
        tangent_x, tangent_y = -vy, vx
        jitter = rng.uniform(-0.85, 0.85)
        dx = vx * math.cos(jitter) + tangent_x * math.sin(jitter)
        dy = vy * math.cos(jitter) + tangent_y * math.sin(jitter)
        length = rng.uniform(5.0, 14.0) * (0.75 + spread * 0.55) * (0.8 + decay_stage * 0.45)
        half_width = rng.uniform(0.7, 1.9) * (0.8 + size * 3.0)
        side_x, side_y = -dy, dx
        base_x = ax - dx * rng.uniform(0.0, 2.5)
        base_y = ay - dy * rng.uniform(0.0, 2.5)
        tip = (ax + dx * length, ay + dy * length)
        shard_tips.append((tip[0], tip[1], dx, dy))
        polygon = [
            (base_x + side_x * half_width, base_y + side_y * half_width),
            (ax + dx * length * 0.45 + side_x * half_width * 0.45, ay + dy * length * 0.45 + side_y * half_width * 0.45),
            tip,
            (ax + dx * length * 0.42 - side_x * half_width * 0.35, ay + dy * length * 0.42 - side_y * half_width * 0.35),
            (base_x - side_x * half_width * 0.65, base_y - side_y * half_width * 0.65),
        ]
        draw.polygon(polygon, fill=cyan if index % 3 else blue)
        if index % 3 == 0:
            kink = rng.uniform(-3.0, 3.0)
            mid = (ax + dx * length * 0.48 + side_x * kink, ay + dy * length * 0.48 + side_y * kink)
            draw.line([(ax, ay), mid, tip], fill=white, width=1)

    # A few tiny detached sparks continue the direction of existing shards.
    # They are intentionally sparse so F7/F8 read as dissipating fragments,
    # not a new particle burst or a central star/blob.
    spark_count = min(12, max(4, round(count * (0.18 + 0.12 * decay_stage))))
    for index in range(spark_count):
        tip_x, tip_y, dx, dy = shard_tips[rng.randrange(len(shard_tips))]
        tangent_x, tangent_y = -dy, dx
        distance = rng.uniform(3.5, 11.0) * (0.85 + decay_stage * 0.35)
        lateral = rng.uniform(-3.0, 3.0)
        x = tip_x + dx * distance + tangent_x * lateral
        y = tip_y + dy * distance + tangent_y * lateral
        radius = rng.uniform(0.35, 0.95)
        color = white if index % 4 == 0 else cyan
        alpha_scale = 0.72 if frame_index == frame_count - 2 else 0.54
        rgba = (color[0], color[1], color[2], round(color[3] * alpha_scale))
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=rgba)
        if index % 5 == 0:
            tail = rng.uniform(1.8, 4.6)
            draw.line([(x - dx * tail, y - dy * tail), (x, y)], fill=rgba, width=1)
    return Image.alpha_composite(frame, overlay)


def apply_decay_to_frames(frame_paths: list[Path], params: dict[str, str | float | int], *, seed: int) -> None:
    frame_count = len(frame_paths)
    for frame_index, frame_path in enumerate(frame_paths):
        frame = Image.open(frame_path).convert("RGBA")
        _add_decay_shards(frame, params, seed=seed, frame_index=frame_index, frame_count=frame_count).save(frame_path)
