from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter


def _hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def _scale_mask(mask: Image.Image, strength: float) -> Image.Image:
    factor = max(0.0, float(strength))
    return mask.point(lambda value: max(0, min(255, round(value * factor))))


def _outside_glow(mask: Image.Image, base_alpha: Image.Image, radius: float, strength: float) -> Image.Image:
    if radius <= 0.0 or strength <= 0.0:
        return Image.new("L", mask.size, 0)
    blurred = mask.filter(ImageFilter.GaussianBlur(radius=float(radius)))
    outside = ImageChops.subtract(blurred, base_alpha)
    return _scale_mask(outside, strength)


def _color_layer(size: tuple[int, int], color: str, alpha: Image.Image) -> Image.Image:
    layer = Image.new("RGBA", size, (*_hex_rgb(color), 0))
    layer.putalpha(alpha)
    return layer


def _energy_masks(frame: Image.Image) -> tuple[Image.Image, Image.Image, Image.Image, Image.Image]:
    rgba = frame.convert("RGBA")
    alpha = rgba.getchannel("A")
    body = Image.new("L", rgba.size, 0)
    inner = Image.new("L", rgba.size, 0)
    core = Image.new("L", rgba.size, 0)
    body_data: list[int] = []
    inner_data: list[int] = []
    core_data: list[int] = []
    for r, g, b, a in rgba.getdata():
        if a <= 8:
            body_data.append(0); inner_data.append(0); core_data.append(0)
            continue
        is_white_energy = r > 180 and g > 195 and b > 205
        is_blue_energy = b > 115 and b >= r * 1.25 and not is_white_energy
        is_cyan_energy = is_blue_energy and g > 90
        body_data.append(a if is_blue_energy else 0)
        inner_data.append(a if is_cyan_energy else 0)
        core_data.append(a if is_white_energy else 0)
    body.putdata(body_data)
    inner.putdata(inner_data)
    core.putdata(core_data)
    return alpha, body, inner, core


def _add_decay_shards(frame: Image.Image, params: dict[str, str | float | int], *, seed: int, frame_index: int, frame_count: int) -> Image.Image:
    """Sharpen the final decay frames with deterministic tapered energy remnants."""
    if frame_count < 2 or frame_index < frame_count - 2:
        return frame
    alpha = frame.getchannel("A")
    active = [(x, y) for y in range(frame.height) for x in range(frame.width) if alpha.getpixel((x, y)) > 110]
    if not active:
        return frame
    xs = [p[0] for p in active]
    ys = [p[1] for p in active]
    cx = (min(xs) + max(xs)) * 0.5
    cy = (min(ys) + max(ys)) * 0.5
    decay_stage = (frame_index - (frame_count - 2) + 1) / 2.0
    rng = random.Random(seed * 1009 + frame_index * 9176 + 73)
    requested = int(params["fragments.count"])
    count = min(28, max(8, round(requested * (0.22 + 0.15 * decay_stage))))
    spread = float(params["fragments.spread"])
    size = float(params["fragments.size"])
    blue = (*_hex_rgb(str(params["colors.body"])), 235)
    cyan = (*_hex_rgb(str(params["colors.inner"])), 245)
    white = (*_hex_rgb(str(params["colors.lightning"])), 245)
    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")

    for i in range(count):
        ax, ay = active[rng.randrange(len(active))]
        vx, vy = ax - cx, ay - cy
        mag = math.hypot(vx, vy) or 1.0
        vx, vy = vx / mag, vy / mag
        tangent_x, tangent_y = -vy, vx
        jitter = rng.uniform(-0.85, 0.85)
        dx = vx * math.cos(jitter) + tangent_x * math.sin(jitter)
        dy = vy * math.cos(jitter) + tangent_y * math.sin(jitter)
        length = rng.uniform(5.0, 14.0) * (0.75 + spread * 0.55) * (0.8 + decay_stage * 0.45)
        half_w = rng.uniform(0.7, 1.9) * (0.8 + size * 3.0)
        sx, sy = -dy, dx
        bx = ax - dx * rng.uniform(0.0, 2.5)
        by = ay - dy * rng.uniform(0.0, 2.5)
        tip = (ax + dx * length, ay + dy * length)
        polygon = [
            (bx + sx * half_w, by + sy * half_w),
            (ax + dx * length * 0.45 + sx * half_w * 0.45, ay + dy * length * 0.45 + sy * half_w * 0.45),
            tip,
            (ax + dx * length * 0.42 - sx * half_w * 0.35, ay + dy * length * 0.42 - sy * half_w * 0.35),
            (bx - sx * half_w * 0.65, by - sy * half_w * 0.65),
        ]
        draw.polygon(polygon, fill=cyan if i % 3 else blue)
        if i % 3 == 0:
            kink = rng.uniform(-3.0, 3.0)
            mid = (ax + dx * length * 0.48 + sx * kink, ay + dy * length * 0.48 + sy * kink)
            draw.line([(ax, ay), mid, tip], fill=white, width=1)

    return Image.alpha_composite(frame, overlay)


def apply_glow(frame_path: Path, params: dict[str, str | float | int]) -> None:
    frame = Image.open(frame_path).convert("RGBA")
    base_alpha, body_mask, inner_mask, core_mask = _energy_masks(frame)
    outer_alpha = _outside_glow(body_mask, base_alpha, float(params["glow.outer_radius"]), float(params["glow.outer_strength"]))
    inner_alpha = _outside_glow(inner_mask, base_alpha, float(params["glow.inner_radius"]), float(params["glow.inner_strength"]))
    core_alpha = _outside_glow(core_mask, base_alpha, float(params["glow.core_radius"]), float(params["glow.core_strength"]))
    composed = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    composed = Image.alpha_composite(composed, _color_layer(frame.size, str(params["colors.outer"]), outer_alpha))
    composed = Image.alpha_composite(composed, _color_layer(frame.size, str(params["colors.inner"]), inner_alpha))
    composed = Image.alpha_composite(composed, _color_layer(frame.size, str(params["colors.core"]), core_alpha))
    composed = Image.alpha_composite(composed, frame)
    composed.save(frame_path)


def apply_glow_to_frames(frame_paths: list[Path], params: dict[str, str | float | int], *, seed: int = 0) -> None:
    frame_count = len(frame_paths)
    for frame_index, frame_path in enumerate(frame_paths):
        frame = Image.open(frame_path).convert("RGBA")
        frame = _add_decay_shards(frame, params, seed=seed, frame_index=frame_index, frame_count=frame_count)
        frame.save(frame_path)
        apply_glow(frame_path, params)
