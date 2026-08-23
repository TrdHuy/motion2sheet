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
            body_data.append(0)
            inner_data.append(0)
            core_data.append(0)
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


def _body_boundary(body_mask: Image.Image) -> tuple[list[tuple[int, int]], tuple[float, float]]:
    binary = body_mask.point(lambda value: 255 if value > 72 else 0)
    eroded = binary.filter(ImageFilter.MinFilter(5))
    boundary = ImageChops.subtract(binary, eroded)
    points: list[tuple[int, int]] = []
    active: list[tuple[int, int]] = []
    pixels = binary.load()
    edge_pixels = boundary.load()
    for y in range(1, binary.height - 1, 2):
        for x in range(1, binary.width - 1, 2):
            if pixels[x, y] > 0:
                active.append((x, y))
            if edge_pixels[x, y] > 0:
                points.append((x, y))
    if not active:
        return [], (binary.width * 0.5, binary.height * 0.5)
    cx = sum(x for x, _ in active) / len(active)
    cy = sum(y for _, y in active) / len(active)
    return points, (cx, cy)


def _spaced_anchors(
    candidates: list[tuple[int, int]],
    count: int,
    rng: random.Random,
    *,
    min_distance: float,
) -> list[tuple[int, int]]:
    if count <= 0 or not candidates:
        return []
    order = list(range(len(candidates)))
    rng.shuffle(order)
    selected: list[tuple[int, int]] = []
    min_distance_sq = min_distance * min_distance
    for index in order:
        point = candidates[index]
        if all((point[0] - x) ** 2 + (point[1] - y) ** 2 >= min_distance_sq for x, y in selected):
            selected.append(point)
            if len(selected) >= count:
                return selected
    while len(selected) < count:
        selected.append(candidates[rng.randrange(len(candidates))])
    return selected


def _bolt_path(
    origin: tuple[float, float],
    direction: tuple[float, float],
    length: float,
    segments: int,
    jitter: float,
    rng: random.Random,
) -> list[tuple[float, float]]:
    dx, dy = _normalize(*direction)
    angle = math.atan2(dy, dx)
    x, y = origin
    points = [(x, y)]
    segment_length = length / max(1, segments)
    for step in range(segments):
        progress = (step + 1) / segments
        angle += rng.uniform(-0.34, 0.34) * jitter * (0.72 + 0.42 * progress)
        step_length = segment_length * rng.uniform(0.78, 1.23)
        dx = math.cos(angle)
        dy = math.sin(angle)
        nx, ny = -dy, dx
        lateral = segment_length * jitter * rng.uniform(-0.34, 0.34)
        x += dx * step_length + nx * lateral
        y += dy * step_length + ny * lateral
        points.append((x, y))
    return points


def _width_profile(
    point_count: int,
    base_width: float,
    tip_width: float,
    jitter: float,
    smoothness: float,
    taper_power: float,
    rng: random.Random,
) -> list[float]:
    if point_count <= 1:
        return [max(tip_width, base_width)]
    raw = [1.0 + rng.uniform(-jitter, jitter) for _ in range(point_count)]
    raw[0] = 1.0 + rng.uniform(-jitter * 0.35, jitter * 0.35)
    for _ in range(2):
        previous = raw[:]
        for index in range(1, point_count - 1):
            local_average = previous[index - 1] * 0.25 + previous[index] * 0.50 + previous[index + 1] * 0.25
            raw[index] = previous[index] * (1.0 - smoothness) + local_average * smoothness
    widths: list[float] = []
    for index, variation in enumerate(raw):
        t = index / (point_count - 1)
        taper = (1.0 - t) ** taper_power
        nominal = tip_width + max(0.0, base_width - tip_width) * taper
        widths.append(max(tip_width * 0.72, nominal * variation))
    widths[-1] = tip_width * rng.uniform(0.72, 1.0)
    return widths


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
        half = width * 0.5
        left.append(((x + nx * half) * scale, (y + ny * half) * scale))
        right.append(((x - nx * half) * scale, (y - ny * half) * scale))
    draw = ImageDraw.Draw(large, "RGBA")
    draw.polygon(left + list(reversed(right)), fill=color)
    if scale > 1:
        large = large.resize(overlay.size, Image.Resampling.LANCZOS)
    overlay.alpha_composite(large)


def _child_direction(points: list[tuple[float, float]], index: int, rng: random.Random) -> tuple[float, float]:
    previous = points[max(0, index - 1)]
    following = points[min(len(points) - 1, index + 1)]
    tx, ty = _normalize(following[0] - previous[0], following[1] - previous[1])
    angle = math.atan2(ty, tx)
    fork = rng.uniform(0.52, 1.05) * (1.0 if rng.random() >= 0.5 else -1.0)
    return math.cos(angle + fork), math.sin(angle + fork)


def _draw_bolt_tree(
    overlay: Image.Image,
    *,
    origin: tuple[float, float],
    direction: tuple[float, float],
    length: float,
    base_width: float,
    params: dict[str, str | float | int],
    rng: random.Random,
    depth: int,
    alpha_scale: float,
) -> None:
    segment_count = 7 if depth == 0 else 5
    jitter = float(params["lightning.jitter"]) * (1.0 + depth * 0.16)
    points = _bolt_path(origin, direction, length, segment_count, jitter, rng)
    tip_width = max(0.10, float(params["lightning.tip_width"]) * (float(params["lightning.minor_width_ratio"]) ** depth))
    widths = _width_profile(
        len(points),
        base_width,
        tip_width,
        float(params["lightning.width_jitter"]),
        float(params["lightning.width_smoothness"]),
        float(params["lightning.taper_power"]),
        rng,
    )
    lightning_rgb = _hex_rgb(str(params["colors.lightning"]))
    core_rgb = _hex_rgb(str(params["colors.core"]))
    outer_alpha = round(225 * alpha_scale)
    core_alpha = round(225 * alpha_scale)
    _draw_tapered_strip(overlay, points, widths, (*lightning_rgb, outer_alpha))
    if depth <= 1:
        _draw_tapered_strip(overlay, points, [max(0.12, width * 0.34) for width in widths], (*core_rgb, core_alpha))

    max_depth = int(params["lightning.branch_depth"])
    if depth >= max_depth:
        return
    probability = float(params["lightning.branch_probability"]) * (0.78 ** depth)
    child_candidates = list(range(2, max(3, len(points) - 1)))
    rng.shuffle(child_candidates)
    child_count = 0
    for index in child_candidates:
        if child_count >= (2 if depth == 0 else 1):
            break
        if rng.random() > probability:
            continue
        child_count += 1
        child_width = widths[index] * float(params["lightning.minor_width_ratio"]) * rng.uniform(0.84, 1.08)
        child_length = length * float(params["lightning.minor_length_ratio"]) * rng.uniform(0.66, 0.94)
        _draw_bolt_tree(
            overlay,
            origin=points[index],
            direction=_child_direction(points, index, rng),
            length=child_length,
            base_width=max(float(params["lightning.tip_width"]) * 1.4, child_width),
            params=params,
            rng=rng,
            depth=depth + 1,
            alpha_scale=alpha_scale * 0.72,
        )


def _add_hierarchical_lightning(
    frame: Image.Image,
    params: dict[str, str | float | int],
    *,
    seed: int,
    frame_index: int,
    frame_count: int,
) -> Image.Image:
    _, body_mask, _, _ = _energy_masks(frame)
    boundary, center = _body_boundary(body_mask)
    if not boundary:
        return frame
    tail_t, head_t, energy, breakup = _motion_window(frame_index, frame_count, float(params["timing.peak"]))
    span_factor = min(1.0, max(0.0, (head_t - tail_t) / 0.50))
    major_target = int(params["lightning.major_count"])
    major_count = max(0, round(major_target * energy * span_factor * (1.0 - 0.34 * breakup)))
    micro_target = int(params["lightning.micro_count"])
    micro_count = max(0, round(micro_target * span_factor * (0.55 + 0.45 * energy + 0.20 * breakup)))
    if major_count == 0 and micro_count == 0:
        return frame

    rng = random.Random(seed * 65537 + frame_index * 8191 + 211)
    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    min_dimension = min(frame.size)
    anchors = _spaced_anchors(boundary, major_count, rng, min_distance=min_dimension * 0.055)
    spread = float(params["lightning.spread"])
    length_scale = float(params["lightning.length"])
    width_min = float(params["lightning.major_width_min"])
    width_max = float(params["lightning.major_width_max"])

    for anchor in anchors:
        outward = _normalize(anchor[0] - center[0], anchor[1] - center[1])
        tangent = (-outward[1], outward[0])
        tangent_bias = rng.uniform(-0.74, 0.74) * spread
        direction = _normalize(outward[0] + tangent[0] * tangent_bias, outward[1] + tangent[1] * tangent_bias)
        length = min_dimension * length_scale * rng.uniform(0.115, 0.205) * (0.72 + 0.28 * energy)
        base_width = rng.uniform(width_min, width_max) * (0.84 + 0.16 * energy)
        _draw_bolt_tree(
            overlay,
            origin=(float(anchor[0]), float(anchor[1])),
            direction=direction,
            length=length,
            base_width=base_width,
            params=params,
            rng=rng,
            depth=0,
            alpha_scale=1.0,
        )

    micro_rgb = _hex_rgb(str(params["colors.lightning"]))
    micro_alpha = round(255 * float(params["lightning.micro_intensity"]))
    micro_width = float(params["lightning.micro_width"])
    for _ in range(micro_count):
        anchor = boundary[rng.randrange(len(boundary))]
        outward = _normalize(anchor[0] - center[0], anchor[1] - center[1])
        tangent = (-outward[1], outward[0])
        tangent_bias = rng.uniform(-1.2, 1.2)
        direction = _normalize(outward[0] * rng.uniform(0.35, 0.95) + tangent[0] * tangent_bias,
                               outward[1] * rng.uniform(0.35, 0.95) + tangent[1] * tangent_bias)
        length = min_dimension * length_scale * rng.uniform(0.025, 0.060)
        points = _bolt_path((float(anchor[0]), float(anchor[1])), direction, length, rng.randint(2, 4),
                            float(params["lightning.jitter"]) * 1.25, rng)
        widths = _width_profile(len(points), micro_width * rng.uniform(0.72, 1.22), 0.10,
                                min(0.70, float(params["lightning.width_jitter"]) * 1.25),
                                float(params["lightning.width_smoothness"]),
                                max(1.0, float(params["lightning.taper_power"])), rng)
        _draw_tapered_strip(overlay, points, widths, (*micro_rgb, micro_alpha), supersample=4)

    return Image.alpha_composite(frame, overlay)


def _add_decay_shards(
    frame: Image.Image,
    params: dict[str, str | float | int],
    *,
    seed: int,
    frame_index: int,
    frame_count: int,
) -> Image.Image:
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
        frame = _add_hierarchical_lightning(
            frame,
            params,
            seed=seed,
            frame_index=frame_index,
            frame_count=frame_count,
        )
        frame = _add_decay_shards(frame, params, seed=seed, frame_index=frame_index, frame_count=frame_count)
        frame.save(frame_path)
        apply_glow(frame_path, params)
