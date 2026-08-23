from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw


def _hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def _smoothstep01(value: float) -> float:
    x = max(0.0, min(1.0, value))
    return x * x * (3.0 - 2.0 * x)


def _motion_window(index: int, frames: int, peak_t: float) -> tuple[float, float, float, float]:
    t = index / max(frames - 1, 1)
    if t <= peak_t:
        growth = _smoothstep01(t / max(peak_t, 1e-6))
        return 0.075 * growth * growth, 0.10 + 0.90 * growth, 0.55 + 0.45 * growth, 0.0
    decay = _smoothstep01((t - peak_t) / max(1e-6, 1.0 - peak_t))
    return 0.075 + 0.845 * decay, 1.0, 1.0 - 0.86 * decay, decay


def _normalize(x: float, y: float) -> tuple[float, float]:
    length = math.hypot(x, y)
    if length <= 1e-6:
        return 1.0, 0.0
    return x / length, y / length


def _arc_point(
    size: tuple[int, int],
    params: dict[str, str | float | int],
    canonical_t: float,
    radial_offset_px: float = 0.0,
) -> tuple[float, float]:
    radius = float(params["radius"])
    angle = math.radians(
        float(params["start_angle"])
        + float(params["arc_angle"]) * canonical_t
        + float(params["rotation"])
    )
    scale = min(size) / max(1e-6, radius * 3.35)
    nx, ny = math.cos(angle), -math.sin(angle)
    x = size[0] * 0.5 + radius * math.cos(angle) * scale + nx * radial_offset_px
    y = size[1] * 0.5 - radius * math.sin(angle) * scale + ny * radial_offset_px
    return x, y


def _smoothed_noise(count: int, jitter: float, smoothness: float, rng: random.Random) -> list[float]:
    values = [rng.uniform(-jitter, jitter) for _ in range(count)]
    for _ in range(3):
        previous = values[:]
        for index in range(1, count - 1):
            local_average = previous[index - 1] * 0.25 + previous[index] * 0.50 + previous[index + 1] * 0.25
            values[index] = previous[index] * (1.0 - smoothness) + local_average * smoothness
    return values


def _draw_tapered_strip(
    overlay: Image.Image,
    points: list[tuple[float, float]],
    widths: list[float],
    color: tuple[int, int, int, int],
    *,
    supersample: int = 3,
) -> None:
    if len(points) < 2 or len(points) != len(widths):
        return
    scale = max(1, supersample)
    large = Image.new("RGBA", (overlay.width * scale, overlay.height * scale), (0, 0, 0, 0))
    left: list[tuple[float, float]] = []
    right: list[tuple[float, float]] = []
    for index, ((x, y), width) in enumerate(zip(points, widths)):
        previous = points[max(0, index - 1)]
        following = points[min(len(points) - 1, index + 1)]
        tx, ty = _normalize(following[0] - previous[0], following[1] - previous[1])
        nx, ny = -ty, tx
        half = max(0.05, width) * 0.5
        left.append(((x + nx * half) * scale, (y + ny * half) * scale))
        right.append(((x - nx * half) * scale, (y - ny * half) * scale))
    draw = ImageDraw.Draw(large, "RGBA")
    draw.polygon(left + list(reversed(right)), fill=color)
    if scale > 1:
        large = large.resize(overlay.size, Image.Resampling.LANCZOS)
    overlay.alpha_composite(large)


def _draw_strip_with_gaps(
    overlay: Image.Image,
    points: list[tuple[float, float]],
    widths: list[float],
    color: tuple[int, int, int, int],
    gaps: list[tuple[float, float]],
) -> None:
    if not gaps:
        _draw_tapered_strip(overlay, points, widths, color, supersample=3)
        return
    count = len(points)
    start: int | None = None
    for index in range(count):
        u = index / max(1, count - 1)
        hidden = any(left <= u <= right for left, right in gaps)
        if not hidden and start is None:
            start = index
        should_flush = start is not None and (hidden or index == count - 1)
        if should_flush:
            end = index if not hidden and index == count - 1 else index - 1
            if end - start >= 1:
                _draw_tapered_strip(overlay, points[start:end + 1], widths[start:end + 1], color, supersample=3)
            start = None


def _recolor_old_core(
    frame: Image.Image,
    params: dict[str, str | float | int],
    tail_t: float,
    head_t: float,
) -> Image.Image:
    """Suppress the old uniform Blender core before drawing the organic replacement."""
    corridor = Image.new("L", frame.size, 0)
    draw = ImageDraw.Draw(corridor)
    samples = 80
    points = [
        _arc_point(frame.size, params, tail_t + (head_t - tail_t) * index / (samples - 1))
        for index in range(samples)
    ]
    corridor_width = max(5, round(float(params["core.width_max"]) * 1.55))
    draw.line(points, fill=255, width=corridor_width, joint="curve")

    rgba = frame.convert("RGBA")
    source = list(rgba.getdata())
    mask = list(corridor.getdata())
    inner_rgb = _hex_rgb(str(params["colors.inner"]))
    result: list[tuple[int, int, int, int]] = []
    for index, (r, g, b, a) in enumerate(source):
        is_white_energy = a > 24 and r > 178 and g > 192 and b > 202
        if mask[index] and is_white_energy:
            result.append((*inner_rgb, a))
        else:
            result.append((r, g, b, a))
    rgba.putdata(result)
    return rgba


def _organic_path_and_widths(
    size: tuple[int, int],
    params: dict[str, str | float | int],
    tail_t: float,
    head_t: float,
    energy: float,
    breakup: float,
    rng: random.Random,
) -> tuple[list[tuple[float, float]], list[float]]:
    sample_count = 68
    width_min = float(params["core.width_min"])
    width_max = float(params["core.width_max"])
    width_jitter = float(params["core.width_jitter"])
    smoothness = float(params["core.width_smoothness"])
    center_jitter = float(params["core.center_jitter"])
    center_frequency = float(params["core.center_frequency"])
    width_noise = _smoothed_noise(sample_count, width_jitter, smoothness, rng)
    center_noise = _smoothed_noise(sample_count, 1.0, min(0.92, smoothness + 0.12), rng)
    phase_a = rng.uniform(0.0, math.tau)
    phase_b = rng.uniform(0.0, math.tau)

    hotspot_count = int(params["core.hotspot_count"])
    hotspot_scale = float(params["core.hotspot_scale"])
    hotspots = [(rng.uniform(0.16, 0.86), rng.uniform(0.035, 0.085), rng.uniform(0.28, 0.62) * hotspot_scale) for _ in range(hotspot_count)]

    points: list[tuple[float, float]] = []
    widths: list[float] = []
    for index in range(sample_count):
        u = index / (sample_count - 1)
        canonical_t = tail_t + (head_t - tail_t) * u
        coherent = (
            math.sin(u * math.tau * center_frequency + phase_a) * 0.62
            + math.sin(u * math.tau * center_frequency * 0.47 + phase_b) * 0.38
        )
        radial = center_jitter * (0.72 * coherent + 0.28 * center_noise[index]) * (0.76 + 0.24 * energy)
        points.append(_arc_point(size, params, canonical_t, radial))

        tail_taper = _smoothstep01(u / 0.10)
        head_taper = _smoothstep01((1.0 - u) / 0.075)
        envelope = tail_taper * head_taper
        body_bias = 0.82 + 0.18 * math.sin(math.pi * u)
        local = 1.0 + width_noise[index]
        hotspot_boost = 0.0
        for center, sigma, amplitude in hotspots:
            hotspot_boost += amplitude * math.exp(-((u - center) ** 2) / max(1e-6, 2.0 * sigma * sigma))
        nominal = width_min + (width_max - width_min) * 0.56
        width = nominal * body_bias * local * (1.0 + hotspot_boost) * envelope
        width *= 0.72 + 0.28 * energy
        width *= 1.0 - 0.20 * breakup
        widths.append(max(0.25, width))
    return points, widths


def _offset_path(
    points: list[tuple[float, float]],
    offset: float,
) -> list[tuple[float, float]]:
    result: list[tuple[float, float]] = []
    for index, (x, y) in enumerate(points):
        previous = points[max(0, index - 1)]
        following = points[min(len(points) - 1, index + 1)]
        tx, ty = _normalize(following[0] - previous[0], following[1] - previous[1])
        nx, ny = -ty, tx
        result.append((x + nx * offset, y + ny * offset))
    return result


def add_organic_core(
    frame: Image.Image,
    params: dict[str, str | float | int],
    *,
    seed: int,
    frame_index: int,
    frame_count: int,
) -> Image.Image:
    tail_t, head_t, energy, breakup = _motion_window(frame_index, frame_count, float(params["timing.peak"]))
    if head_t - tail_t < 0.045:
        return frame

    rng = random.Random(seed * 104729 + frame_index * 7919 + 503)
    base = _recolor_old_core(frame, params, tail_t, head_t)
    points, widths = _organic_path_and_widths(base.size, params, tail_t, head_t, energy, breakup, rng)
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    core_rgb = _hex_rgb(str(params["colors.core"]))
    lightning_rgb = _hex_rgb(str(params["colors.lightning"]))

    gaps: list[tuple[float, float]] = []
    split_probability = float(params["core.split_probability"])
    if rng.random() < split_probability * (0.72 + 0.28 * energy):
        for _ in range(1 + (1 if rng.random() < split_probability * 0.45 else 0)):
            center = rng.uniform(0.20, 0.82)
            half = rng.uniform(0.010, 0.026)
            gaps.append((center - half, center + half))

    _draw_strip_with_gaps(overlay, points, widths, (*core_rgb, 242), gaps)

    streak_count = int(params["core.streak_count"])
    streak_ratio = float(params["core.streak_width_ratio"])
    for streak_index in range(streak_count):
        start_u = rng.uniform(0.05, 0.58)
        span = rng.uniform(0.18, 0.50)
        end_u = min(0.96, start_u + span)
        start = max(0, round(start_u * (len(points) - 1)))
        end = min(len(points) - 1, round(end_u * (len(points) - 1)))
        if end - start < 3:
            continue
        offset = rng.uniform(-0.58, 0.58) * float(params["core.width_max"])
        streak_points = _offset_path(points[start:end + 1], offset)
        streak_widths = [
            max(0.35, width * streak_ratio * rng.uniform(0.72, 1.18))
            for width in widths[start:end + 1]
        ]
        color = (*core_rgb, rng.randint(150, 218)) if streak_index % 2 == 0 else (*lightning_rgb, rng.randint(145, 205))
        _draw_tapered_strip(overlay, streak_points, streak_widths, color, supersample=4)

    hotspot_count = int(params["core.hotspot_count"])
    hotspot_scale = float(params["core.hotspot_scale"])
    hot = Image.new("RGBA", base.size, (0, 0, 0, 0))
    hot_draw = ImageDraw.Draw(hot, "RGBA")
    for _ in range(hotspot_count):
        index = rng.randint(max(1, len(points) // 8), max(1, len(points) - len(points) // 8 - 1))
        x, y = points[index]
        radius = max(1.2, widths[index] * hotspot_scale * rng.uniform(0.22, 0.45))
        hot_draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(*core_rgb, rng.randint(135, 205)))
    overlay = Image.alpha_composite(overlay, hot)

    return Image.alpha_composite(base, overlay)
