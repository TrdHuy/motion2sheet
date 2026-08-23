from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .energy_graph import EnergyGraph, EnergyNode, build_energy_graph, normalize


def _hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def _to_linear(channel: int) -> float:
    value = channel / 255.0
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def _from_linear(value: float) -> int:
    value = max(0.0, min(1.0, value))
    encoded = value * 12.92 if value <= 0.0031308 else 1.055 * (value ** (1.0 / 2.4)) - 0.055
    return max(0, min(255, round(encoded * 255.0)))


def _mix_linear(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    result: list[int] = []
    for left, right in zip(a, b):
        linear = _to_linear(left) * (1.0 - t) + _to_linear(right) * t
        result.append(_from_linear(linear))
    return result[0], result[1], result[2]


def _gradient_color(energy: float, params: dict[str, str | float | int]) -> tuple[int, int, int]:
    outer = _hex_rgb(str(params["colors.outer"]))
    body = _hex_rgb(str(params["colors.body"]))
    inner = _hex_rgb(str(params["colors.inner"]))
    core = _hex_rgb(str(params["colors.core"]))
    cyan_threshold = float(params["energy.cyan_threshold"])
    white_threshold = float(params["energy.white_threshold"])
    if energy <= 0.34:
        return _mix_linear(outer, body, energy / 0.34)
    if energy <= cyan_threshold:
        return _mix_linear(body, inner, (energy - 0.34) / max(1e-6, cyan_threshold - 0.34))
    if energy <= white_threshold:
        return _mix_linear(inner, _mix_linear(inner, core, 0.24), (energy - cyan_threshold) / max(1e-6, white_threshold - cyan_threshold))
    return _mix_linear(inner, core, (energy - white_threshold) / max(1e-6, 1.0 - white_threshold))


def _base_energy_field(
    frame: Image.Image,
    params: dict[str, str | float | int],
    *,
    seed: int,
    frame_index: int,
) -> tuple[Image.Image, Image.Image]:
    rgba = frame.convert("RGBA")
    alpha = rgba.getchannel("A")
    result = Image.new("L", rgba.size, 0)
    values: list[int] = []
    turbulence = float(params["energy.turbulence"])
    frequency = float(params["energy.turbulence_frequency"])
    body_floor = float(params["energy.body_floor"])
    body_gain = float(params["energy.body_gain"])
    phase = (seed * 0.000731 + frame_index * 0.619) % math.tau
    width, height = rgba.size
    for index, (r, g, b, a) in enumerate(rgba.getdata()):
        if a <= 5:
            values.append(0)
            continue
        x, y = index % width, index // width
        if r > 175 and g > 188 and b > 198:
            base = 0.59
        elif b > 125 and g > 85 and b >= r * 1.12:
            base = 0.50 + min(0.09, g / 255.0 * 0.08)
        elif b > 95:
            base = 0.34 + min(0.08, b / 255.0 * 0.06)
        else:
            base = body_floor
        wave = (
            math.sin((x / width) * math.tau * frequency + phase) * 0.55
            + math.sin((y / height) * math.tau * frequency * 0.73 - phase * 0.7) * 0.30
            + math.sin(((x + y) / (width + height)) * math.tau * frequency * 1.63 + phase * 1.4) * 0.15
        )
        energy = max(body_floor, min(0.68, base * body_gain + turbulence * wave))
        energy *= (a / 255.0) ** 0.30
        values.append(round(max(0.0, min(1.0, energy)) * 255.0))
    result.putdata(values)
    return result.filter(ImageFilter.GaussianBlur(0.7)), alpha


def _draw_variable_strip(mask: Image.Image, points: list[tuple[float, float]], widths: list[float], values: list[int]) -> None:
    if len(points) < 2:
        return
    draw = ImageDraw.Draw(mask)
    for index in range(len(points) - 1):
        p0, p1 = points[index], points[index + 1]
        width = max(1, round((widths[index] + widths[index + 1]) * 0.5))
        value = max(values[index], values[index + 1])
        draw.line([p0, p1], fill=value, width=width)
        radius = max(1, width // 2)
        for x, y in (p0, p1):
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=value)


def _graph_core_mask(graph: EnergyGraph, size: tuple[int, int], params: dict[str, str | float | int], rng: random.Random) -> Image.Image:
    mask = Image.new("L", size, 0)
    points = [node.point for node in graph.nodes]
    widths = [node.width for node in graph.nodes]
    values = [round(255 * node.energy) for node in graph.nodes]
    split_probability = float(params["core.split_probability"])
    if rng.random() < split_probability * (0.72 + 0.28 * graph.energy):
        for _ in range(1 + (1 if rng.random() < split_probability * 0.45 else 0)):
            center = rng.randint(round(len(points) * 0.20), round(len(points) * 0.82))
            half = rng.randint(1, 2)
            for index in range(max(0, center - half), min(len(values), center + half + 1)):
                values[index] = min(values[index], 185)
    _draw_variable_strip(mask, points, widths, values)

    streak_count = int(params["core.streak_count"])
    streak_ratio = float(params["core.streak_width_ratio"])
    for _ in range(streak_count):
        start = rng.randint(3, max(4, len(graph.nodes) - 24))
        end = min(len(graph.nodes) - 2, start + rng.randint(10, 28))
        offset = rng.uniform(-0.55, 0.55) * float(params["core.width_max"])
        streak_points: list[tuple[float, float]] = []
        streak_widths: list[float] = []
        streak_values: list[int] = []
        for node in graph.nodes[start:end + 1]:
            streak_points.append((node.point[0] + node.normal[0] * offset, node.point[1] + node.normal[1] * offset))
            streak_widths.append(max(1.0, node.width * streak_ratio * rng.uniform(0.72, 1.18)))
            streak_values.append(rng.randint(205, 238))
        _draw_variable_strip(mask, streak_points, streak_widths, streak_values)
    return mask.filter(ImageFilter.GaussianBlur(0.45))


def _bolt_path_from_node(node: EnergyNode, length: float, segments: int, jitter: float, rng: random.Random) -> list[tuple[float, float]]:
    tangent = node.tangent
    normal = node.normal
    root_inside = (
        node.point[0] - normal[0] * node.width * 0.24 - tangent[0] * node.width * 0.12,
        node.point[1] - normal[1] * node.width * 0.24 - tangent[1] * node.width * 0.12,
    )
    root_mid = node.point
    root_edge = (node.point[0] + normal[0] * node.width * 0.58, node.point[1] + normal[1] * node.width * 0.58)
    points = [root_inside, root_mid, root_edge]
    tangent_bias = rng.uniform(-0.72, 0.72)
    dx, dy = normalize(normal[0] + tangent[0] * tangent_bias, normal[1] + tangent[1] * tangent_bias)
    angle = math.atan2(dy, dx)
    x, y = root_edge
    remaining = max(1.0, length - node.width * 0.58)
    step_length = remaining / max(1, segments)
    for step in range(segments):
        progress = (step + 1) / segments
        angle += rng.uniform(-0.38, 0.38) * jitter * (0.74 + progress * 0.35)
        local_step = step_length * rng.uniform(0.78, 1.23)
        dx, dy = math.cos(angle), math.sin(angle)
        nx, ny = -dy, dx
        lateral = step_length * jitter * rng.uniform(-0.32, 0.32)
        x += dx * local_step + nx * lateral
        y += dy * local_step + ny * lateral
        points.append((x, y))
    return points


def _width_profile(count: int, base: float, tip: float, params: dict[str, str | float | int], rng: random.Random) -> list[float]:
    jitter = float(params["lightning.width_jitter"])
    smoothness = float(params["lightning.width_smoothness"])
    taper_power = float(params["lightning.taper_power"])
    raw = [1.0 + rng.uniform(-jitter, jitter) for _ in range(count)]
    for _ in range(2):
        previous = raw[:]
        for index in range(1, count - 1):
            avg = previous[index - 1] * 0.25 + previous[index] * 0.50 + previous[index + 1] * 0.25
            raw[index] = previous[index] * (1.0 - smoothness) + avg * smoothness
    widths: list[float] = []
    for index, variation in enumerate(raw):
        t = index / max(1, count - 1)
        nominal = tip + max(0.0, base - tip) * ((1.0 - t) ** taper_power)
        widths.append(max(tip * 0.72, nominal * variation))
    widths[-1] = tip * rng.uniform(0.72, 1.0)
    return widths


def _child_direction(points: list[tuple[float, float]], index: int, rng: random.Random) -> tuple[float, float]:
    previous = points[max(0, index - 1)]
    following = points[min(len(points) - 1, index + 1)]
    tx, ty = normalize(following[0] - previous[0], following[1] - previous[1])
    angle = math.atan2(ty, tx) + rng.uniform(0.55, 1.05) * (1.0 if rng.random() > 0.5 else -1.0)
    return math.cos(angle), math.sin(angle)


def _free_bolt_path(origin: tuple[float, float], direction: tuple[float, float], length: float, segments: int, jitter: float, rng: random.Random) -> list[tuple[float, float]]:
    dx, dy = normalize(*direction)
    angle = math.atan2(dy, dx)
    x, y = origin
    points = [(x, y)]
    step = length / max(1, segments)
    for _ in range(segments):
        angle += rng.uniform(-0.42, 0.42) * jitter
        local = step * rng.uniform(0.76, 1.22)
        x += math.cos(angle) * local
        y += math.sin(angle) * local
        points.append((x, y))
    return points


def _draw_bolt_tree(mask: Image.Image, points: list[tuple[float, float]], widths: list[float], params: dict[str, str | float | int], rng: random.Random, depth: int) -> None:
    values = [245 if depth == 0 else 228 for _ in points]
    _draw_variable_strip(mask, points, widths, values)
    if depth >= int(params["lightning.branch_depth"]):
        return
    probability = float(params["lightning.branch_probability"]) * (0.78 ** depth)
    candidates = list(range(3, max(4, len(points) - 2)))
    rng.shuffle(candidates)
    spawned = 0
    for index in candidates:
        if spawned >= (2 if depth == 0 else 1) or rng.random() > probability:
            continue
        spawned += 1
        child_direction = _child_direction(points, index, rng)
        child_length = math.dist(points[0], points[-1]) * float(params["lightning.minor_length_ratio"]) * rng.uniform(0.66, 0.94)
        child_points = _free_bolt_path(points[index], child_direction, child_length, 5, float(params["lightning.jitter"]) * 1.12, rng)
        child_base = widths[index] * float(params["lightning.minor_width_ratio"]) * rng.uniform(0.84, 1.08)
        child_widths = _width_profile(len(child_points), max(0.55, child_base), max(0.12, float(params["lightning.tip_width"]) * 0.75), params, rng)
        _draw_bolt_tree(mask, child_points, child_widths, params, rng, depth + 1)


def _graph_lightning_mask(graph: EnergyGraph, size: tuple[int, int], params: dict[str, str | float | int], rng: random.Random) -> Image.Image:
    mask = Image.new("L", size, 0)
    span = min(1.0, max(0.0, (graph.head_t - graph.tail_t) / 0.50))
    target = int(params["lightning.major_count"])
    count = max(0, round(target * graph.energy * span * (1.0 - 0.30 * graph.breakup)))
    min_dim = min(size)
    for index in graph.major_anchor_indices(count, rng):
        node = graph.nodes[index]
        length = min_dim * float(params["lightning.length"]) * rng.uniform(0.14, 0.22) * (0.78 + 0.22 * graph.energy)
        points = _bolt_path_from_node(node, length, 7, float(params["lightning.jitter"]), rng)
        base = rng.uniform(float(params["lightning.major_width_min"]), float(params["lightning.major_width_max"]))
        root_base = max(base, node.width * float(params["energy.root_width_coupling"]))
        widths = _width_profile(len(points), root_base, float(params["lightning.tip_width"]), params, rng)
        widths[0] = max(widths[0], node.width * 0.62)
        widths[1] = max(widths[1], node.width * 0.72)
        _draw_bolt_tree(mask, points, widths, params, rng, 0)

    micro_target = int(params["lightning.micro_count"])
    micro_count = max(0, round(micro_target * span * (0.55 + 0.45 * graph.energy)))
    for _ in range(micro_count):
        node = graph.nodes[rng.randint(2, len(graph.nodes) - 3)]
        direction = normalize(
            node.normal[0] + node.tangent[0] * rng.uniform(-1.1, 1.1),
            node.normal[1] + node.tangent[1] * rng.uniform(-1.1, 1.1),
        )
        length = min_dim * float(params["lightning.length"]) * rng.uniform(0.025, 0.055)
        points = _free_bolt_path(node.point, direction, length, rng.randint(2, 4), float(params["lightning.jitter"]) * 1.25, rng)
        widths = _width_profile(len(points), float(params["lightning.micro_width"]) * rng.uniform(0.72, 1.20), 0.12, params, rng)
        values = [round(255 * float(params["lightning.micro_intensity"])) for _ in points]
        _draw_variable_strip(mask, points, widths, values)
    return mask.filter(ImageFilter.GaussianBlur(0.35))


def _combine_field(base: Image.Image, core: Image.Image, lightning: Image.Image, params: dict[str, str | float | int]) -> Image.Image:
    core_gain = float(params["energy.core_gain"])
    lightning_gain = float(params["energy.lightning_gain"])
    values: list[int] = []
    for base_value, core_value, lightning_value in zip(base.getdata(), core.getdata(), lightning.getdata()):
        energy = base_value / 255.0
        energy = max(energy, min(1.0, (core_value / 255.0) * core_gain))
        energy = max(energy, min(1.0, (lightning_value / 255.0) * lightning_gain))
        values.append(round(max(0.0, min(1.0, energy)) * 255.0))
    result = Image.new("L", base.size, 0)
    result.putdata(values)
    return result


def _render_energy_rgba(base_alpha: Image.Image, field: Image.Image, params: dict[str, str | float | int]) -> Image.Image:
    wide = field.filter(ImageFilter.GaussianBlur(float(params["energy.glow_radius"])))
    tight = field.filter(ImageFilter.GaussianBlur(max(0.5, float(params["energy.glow_radius"]) * 0.35)))
    alpha_power = float(params["energy.alpha_power"])
    alpha_gain = float(params["energy.alpha_gain"])
    glow_strength = float(params["energy.glow_strength"])
    outer = _hex_rgb(str(params["colors.outer"]))
    inner = _hex_rgb(str(params["colors.inner"]))
    output: list[tuple[int, int, int, int]] = []
    for base_a, raw_energy, raw_wide, raw_tight in zip(base_alpha.getdata(), field.getdata(), wide.getdata(), tight.getdata()):
        energy = raw_energy / 255.0
        glow = raw_wide / 255.0
        tight_glow = raw_tight / 255.0
        if energy <= 0.002 and glow <= 0.004:
            output.append((0, 0, 0, 0))
            continue
        rgb = _gradient_color(energy, params)
        linear = [_to_linear(channel) for channel in rgb]
        for index, channel in enumerate(outer):
            linear[index] += _to_linear(channel) * glow * glow_strength * 0.24
        for index, channel in enumerate(inner):
            linear[index] += _to_linear(channel) * tight_glow * glow_strength * 0.08
        final_rgb = tuple(_from_linear(channel) for channel in linear)
        field_alpha = (energy ** alpha_power) * alpha_gain
        body_alpha = (base_a / 255.0) * float(params["energy.base_alpha_mix"])
        glow_alpha = glow * glow_strength * 0.24
        alpha = round(max(body_alpha, field_alpha, glow_alpha) * 255.0)
        output.append((final_rgb[0], final_rgb[1], final_rgb[2], max(0, min(255, alpha))))
    image = Image.new("RGBA", field.size, (0, 0, 0, 0))
    image.putdata(output)
    return image


def apply_energy_graph(
    frame: Image.Image,
    params: dict[str, str | float | int],
    *,
    seed: int,
    frame_index: int,
    frame_count: int,
) -> Image.Image:
    graph = build_energy_graph(frame.size, params, seed=seed, frame_index=frame_index, frame_count=frame_count)
    rng = random.Random(seed * 65537 + frame_index * 8191 + 991)
    base, base_alpha = _base_energy_field(frame, params, seed=seed, frame_index=frame_index)
    core = _graph_core_mask(graph, frame.size, params, rng)
    lightning = _graph_lightning_mask(graph, frame.size, params, rng)
    field = _combine_field(base, core, lightning, params)
    return _render_energy_rgba(base_alpha, field, params)


def apply_energy_graph_to_frames(frame_paths: list[Path], params: dict[str, str | float | int], *, seed: int) -> None:
    frame_count = len(frame_paths)
    for frame_index, frame_path in enumerate(frame_paths):
        frame = Image.open(frame_path).convert("RGBA")
        apply_energy_graph(frame, params, seed=seed, frame_index=frame_index, frame_count=frame_count).save(frame_path)
