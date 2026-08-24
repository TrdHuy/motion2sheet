from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


def _smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def dissolve_progress(params: dict[str, str | float | int], frame_index: int, frame_count: int, *, core: bool = False) -> float:
    strength = float(params["dissolve.strength"])
    if strength <= 0.0 or frame_count < 2:
        return 0.0
    start = float(params["dissolve.start"])
    if core:
        start = min(float(params["dissolve.end"]), start + float(params["dissolve.core_delay"]))
    end = float(params["dissolve.end"])
    t = frame_index / max(1, frame_count - 1)
    if t <= start:
        return 0.0
    if t >= end:
        return strength
    return strength * _smoothstep((t - start) / max(1e-6, end - start))


def _noise_field(size: tuple[int, int], params: dict[str, str | float | int], *, seed: int) -> Image.Image:
    width, height = size
    min_dim = min(size)
    scale = float(params["dissolve.noise_scale"])
    detail = float(params["dissolve.noise_detail"])
    cell = max(3, round(min_dim * scale * 0.24))
    rng = random.Random(seed * 32452843 + 179)

    def octave(divisor: float, weight: float) -> tuple[Image.Image, float]:
        local_cell = max(2, round(cell / divisor))
        grid_w = max(2, math.ceil(width / local_cell) + 1)
        grid_h = max(2, math.ceil(height / local_cell) + 1)
        data = [rng.randrange(256) for _ in range(grid_w * grid_h)]
        image = Image.new("L", (grid_w, grid_h), 0)
        image.putdata(data)
        return image.resize(size, Image.Resampling.BICUBIC), weight

    layers = [octave(1.0, 0.58)]
    if detail >= 2.0:
        layers.append(octave(2.0, 0.27))
    if detail >= 3.0:
        layers.append(octave(4.0, 0.15))
    if detail >= 5.0:
        layers.append(octave(8.0, 0.08))
    total = sum(weight for _, weight in layers)
    values = []
    pixel_layers = [list(image.getdata()) for image, _ in layers]
    weights = [weight for _, weight in layers]
    for index in range(width * height):
        values.append(round(sum(pixels[index] * weight for pixels, weight in zip(pixel_layers, weights)) / total))
    result = Image.new("L", size, 0)
    result.putdata(values)
    return result


def _layer_amount(r: int, g: int, b: int, params: dict[str, str | float | int]) -> tuple[float, bool]:
    # Lõi trắng/cyan sáng được cho tan trễ hơn; thân xanh tan sớm nhất.
    if r >= 150 and g >= 170 and b >= 180:
        return float(params["dissolve.core_amount"]), True
    if g >= 105 and b >= 160:
        return float(params["dissolve.inner_amount"]), False
    return float(params["dissolve.body_amount"]), False


def _apply_breakup(
    frame: Image.Image,
    noise: Image.Image,
    params: dict[str, str | float | int],
    *,
    frame_index: int,
    frame_count: int,
) -> tuple[Image.Image, list[tuple[int, int, tuple[int, int, int, int], float]]]:
    base_progress = dissolve_progress(params, frame_index, frame_count)
    core_progress = dissolve_progress(params, frame_index, frame_count, core=True)
    if base_progress <= 0.0:
        return frame, []

    softness = float(params["dissolve.edge_softness"])
    source = frame.convert("RGBA")
    rgba = list(source.getdata())
    noise_values = list(noise.getdata())
    output = []
    removed: list[tuple[int, int, tuple[int, int, int, int], float]] = []
    width = source.width

    for index, ((r, g, b, a), noise_value) in enumerate(zip(rgba, noise_values)):
        if a <= 2:
            output.append((r, g, b, a))
            continue
        amount, is_core = _layer_amount(r, g, b, params)
        progress = (core_progress if is_core else base_progress) * amount
        if progress <= 0.0:
            output.append((r, g, b, a))
            continue
        threshold = progress
        n = noise_value / 255.0
        edge = max(0.002, softness)
        erase = _smoothstep((threshold + edge - n) / (2.0 * edge))
        erase = max(0.0, min(1.0, erase))
        new_alpha = round(a * (1.0 - erase))
        output.append((r, g, b, new_alpha))
        if erase > 0.34 and a > 40:
            removed.append((index % width, index // width, (r, g, b, a), erase))

    result = Image.new("RGBA", source.size, (0, 0, 0, 0))
    result.putdata(output)
    return result, removed


def _detached_overlay(
    size: tuple[int, int],
    removed: list[tuple[int, int, tuple[int, int, int, int], float]],
    params: dict[str, str | float | int],
    *,
    seed: int,
    frame_index: int,
    frame_count: int,
) -> Image.Image:
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    progress = dissolve_progress(params, frame_index, frame_count)
    if progress <= 0.0 or not removed:
        return overlay

    rng = random.Random(seed * 49979687 + frame_index * 8191 + 421)
    draw = ImageDraw.Draw(overlay, "RGBA")
    cx, cy = size[0] * 0.5, size[1] * 0.5
    fragment_count = round(int(params["dissolve.fragment_count"]) * progress)
    spark_count = round(int(params["dissolve.spark_count"]) * progress)
    fragment_size = min(size) * float(params["dissolve.fragment_size"])
    spread = float(params["dissolve.fragment_spread"])
    drift = min(size) * float(params["dissolve.fragment_drift"]) * progress

    for _ in range(fragment_count):
        x, y, color, erase = removed[rng.randrange(len(removed))]
        vx, vy = x - cx, y - cy
        magnitude = math.hypot(vx, vy) or 1.0
        vx, vy = vx / magnitude, vy / magnitude
        tx, ty = -vy, vx
        side = rng.uniform(-1.0, 1.0) * spread
        dx, dy = vx + tx * side, vy + ty * side
        dmag = math.hypot(dx, dy) or 1.0
        dx, dy = dx / dmag, dy / dmag
        distance = drift * rng.uniform(0.25, 1.0)
        px, py = x + dx * distance, y + dy * distance
        length = fragment_size * rng.uniform(0.20, 0.75)
        half = fragment_size * rng.uniform(0.04, 0.15)
        sx, sy = -dy, dx
        alpha = round(min(235, color[3] * erase * (0.90 - 0.34 * progress)))
        draw.polygon([
            (px - dx * length * 0.25 + sx * half, py - dy * length * 0.25 + sy * half),
            (px + dx * length, py + dy * length),
            (px - dx * length * 0.15 - sx * half, py - dy * length * 0.15 - sy * half),
        ], fill=(color[0], color[1], color[2], alpha))

    spark_length = min(size) * float(params["dissolve.spark_length"])
    for _ in range(spark_count):
        x, y, color, erase = removed[rng.randrange(len(removed))]
        vx, vy = x - cx, y - cy
        magnitude = math.hypot(vx, vy) or 1.0
        vx, vy = vx / magnitude, vy / magnitude
        angle = rng.uniform(-0.70, 0.70) * spread
        dx = vx * math.cos(angle) - vy * math.sin(angle)
        dy = vx * math.sin(angle) + vy * math.cos(angle)
        length = spark_length * rng.uniform(0.20, 0.80) * progress
        alpha = round(min(220, 190 * erase))
        draw.line([(x, y), (x + dx * length, y + dy * length)], fill=(max(color[0], 80), max(color[1], 180), 255, alpha), width=1)

    glow = overlay.getchannel("A").filter(ImageFilter.GaussianBlur(2.2))
    glow_layer = Image.new("RGBA", size, (18, 150, 255, 0))
    glow_layer.putalpha(glow.point(lambda value: round(value * 0.22)))
    return Image.alpha_composite(glow_layer, overlay)


def add_dissolve(
    frame: Image.Image,
    params: dict[str, str | float | int],
    *,
    seed: int,
    frame_index: int,
    frame_count: int,
) -> Image.Image:
    # Fast no-op is part of the compatibility contract: strength=0 must preserve pixels.
    if float(params["dissolve.strength"]) <= 0.0:
        return frame
    if dissolve_progress(params, frame_index, frame_count) <= 0.0:
        return frame
    noise = _noise_field(frame.size, params, seed=seed)
    dissolved, removed = _apply_breakup(frame, noise, params, frame_index=frame_index, frame_count=frame_count)
    fragments = _detached_overlay(frame.size, removed, params, seed=seed, frame_index=frame_index, frame_count=frame_count)
    return Image.alpha_composite(dissolved, fragments)


def apply_dissolve_to_frames(
    frame_paths: list[Path],
    params: dict[str, str | float | int],
    *,
    seed: int,
) -> None:
    if float(params["dissolve.strength"]) <= 0.0:
        return
    frame_count = len(frame_paths)
    for frame_index, frame_path in enumerate(frame_paths):
        frame = Image.open(frame_path).convert("RGBA")
        result = add_dissolve(frame, params, seed=seed, frame_index=frame_index, frame_count=frame_count)
        if result is not frame:
            result.save(frame_path)
