from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageFilter

from .energy_graph import EnergyGraph, EnergyNode, normalize


def _smoothstep01(value: float) -> float:
    x = max(0.0, min(1.0, value))
    return x * x * (3.0 - 2.0 * x)


def _draw_variable_strip(
    mask: Image.Image,
    points: list[tuple[float, float]],
    widths: list[float],
    value: int,
) -> None:
    if len(points) < 2 or len(points) != len(widths):
        return
    draw = ImageDraw.Draw(mask)
    for index in range(len(points) - 1):
        p0, p1 = points[index], points[index + 1]
        width = max(1, round((widths[index] + widths[index + 1]) * 0.5))
        local_value = max(0, min(255, round(value * (0.93 + 0.07 * (1.0 - index / max(1, len(points) - 1))))))
        # Connected thick segments are enough; per-node circles created the
        # scalloped/bubbly silhouette seen in earlier runs.
        draw.line([p0, p1], fill=local_value, width=width)


def _mass_path(
    graph: EnergyGraph,
    params: dict[str, str | float | int],
    rng: random.Random,
    *,
    phase: float,
    normal_scale: float,
    normal_shift: float,
) -> tuple[list[tuple[float, float]], list[float]]:
    body_scale = float(params["shape.body_scale"])
    form_noise = float(params["shape.form_noise"])
    frequency = float(params["shape.form_noise_frequency"])
    detail_noise = float(params["shape.detail_noise"])
    points: list[tuple[float, float]] = []
    widths: list[float] = []
    previous_width_noise = rng.uniform(-0.08, 0.08)
    for node in graph.nodes:
        u = node.u
        coherent = (
            math.sin(u * math.tau * frequency + phase) * 0.68
            + math.sin(u * math.tau * frequency * 0.47 - phase * 0.63) * 0.32
        )
        local_shift = normal_shift * node.width + coherent * form_noise * 4.5 * normal_scale
        points.append((
            node.point[0] + node.normal[0] * local_shift,
            node.point[1] + node.normal[1] * local_shift,
        ))
        target_noise = rng.uniform(-detail_noise * 0.14, detail_noise * 0.14)
        previous_width_noise = previous_width_noise * 0.70 + target_noise * 0.30
        envelope = _smoothstep01(u / 0.065) * _smoothstep01((1.0 - u) / 0.050)
        width = node.width * body_scale * normal_scale * (1.0 + previous_width_noise) * envelope
        widths.append(max(0.5, width))
    return points, widths


def _wisp_path(
    node: EnergyNode,
    *,
    length: float,
    curvature: float,
    spread: float,
    rng: random.Random,
    tangent_sign: float | None = None,
    normal_bias_override: float | None = None,
) -> list[tuple[float, float]]:
    if tangent_sign is None:
        tangent_sign = 1.0 if rng.random() > 0.18 else -1.0
    tx, ty = node.tangent[0] * tangent_sign, node.tangent[1] * tangent_sign
    nx, ny = node.normal
    normal_bias = normal_bias_override if normal_bias_override is not None else rng.uniform(-0.24, 0.82) * spread
    dx, dy = normalize(tx + nx * normal_bias, ty + ny * normal_bias)
    px, py = -dy, dx
    root_depth = rng.uniform(-0.34, 0.16) * node.width
    root = (
        node.point[0] + node.normal[0] * root_depth,
        node.point[1] + node.normal[1] * root_depth,
    )
    count = rng.randint(9, 14)
    bend_sign = 1.0 if rng.random() > 0.5 else -1.0
    phase = rng.uniform(0.0, math.tau)
    frequency = rng.uniform(0.62, 1.12)
    points: list[tuple[float, float]] = []
    for index in range(count):
        u = index / (count - 1)
        advance = length * (u ** 0.90)
        bend = math.sin(math.pi * u) * length * curvature * 0.18 * bend_sign
        wave = math.sin(u * math.tau * frequency + phase) * length * 0.028 * (1.0 - u)
        points.append((
            root[0] + dx * advance + px * (bend + wave),
            root[1] + dy * advance + py * (bend + wave),
        ))
    return points


def _wisp_widths(root_width: float, count: int, rng: random.Random, *, taper_power: float = 1.55) -> list[float]:
    widths: list[float] = []
    local = 1.0
    for index in range(count):
        u = index / max(1, count - 1)
        local = local * 0.76 + rng.uniform(0.80, 1.16) * 0.24
        taper = (1.0 - u) ** taper_power
        widths.append(max(0.20, root_width * local * taper))
    widths[-1] = min(widths[-1], 0.22)
    return widths


def _draw_terminal_flows(
    mask: Image.Image,
    graph: EnergyGraph,
    params: dict[str, str | float | int],
    rng: random.Random,
) -> None:
    if len(graph.nodes) < 12:
        return
    min_dim = min(mask.size)
    curvature = float(params["shape.tongue_curve"])
    width_control = float(params["shape.tongue_width"])
    length_control = float(params["shape.tongue_length"])
    anchors = [
        (graph.nodes[max(3, len(graph.nodes) - 8)], 1.0, 1.24),
        (graph.nodes[max(3, len(graph.nodes) - 14)], 1.0, 0.98),
        (graph.nodes[min(len(graph.nodes) - 4, 7)], -1.0, 1.00),
        (graph.nodes[min(len(graph.nodes) - 4, 13)], -1.0, 0.78),
    ]
    for index, (node, tangent_sign, strength) in enumerate(anchors):
        # Contract F5 has long, broad tangent streams reaching toward the open
        # side of the crescent; these intentionally span ~45-60% of a frame.
        length = min_dim * (0.20 + length_control * 0.28) * strength * rng.uniform(0.92, 1.10)
        normal_bias = rng.uniform(-0.14, 0.24)
        points = _wisp_path(
            node,
            length=length,
            curvature=curvature * rng.uniform(0.58, 0.82),
            spread=0.40,
            rng=rng,
            tangent_sign=tangent_sign,
            normal_bias_override=normal_bias,
        )
        root_width = max(2.0, node.width * width_control * rng.uniform(1.12, 1.55))
        widths = _wisp_widths(root_width, len(points), rng, taper_power=rng.uniform(1.28, 1.50))
        value = rng.randint(126, 150) if index < 2 else rng.randint(112, 140)
        _draw_variable_strip(mask, points, widths, value)

        if index < 3:
            offset_node = EnergyNode(
                node.u,
                (node.point[0] - node.normal[0] * node.width * 0.38, node.point[1] - node.normal[1] * node.width * 0.38),
                node.tangent,
                node.normal,
                node.width * 0.78,
                node.energy,
            )
            parallel = _wisp_path(
                offset_node,
                length=length * rng.uniform(0.72, 0.92),
                curvature=curvature * rng.uniform(0.48, 0.72),
                spread=0.30,
                rng=rng,
                tangent_sign=tangent_sign,
                normal_bias_override=normal_bias + rng.uniform(-0.08, 0.08),
            )
            parallel_widths = _wisp_widths(root_width * rng.uniform(0.56, 0.76), len(parallel), rng, taper_power=1.42)
            _draw_variable_strip(mask, parallel, parallel_widths, max(96, value - 18))


def build_energy_mass_field(
    size: tuple[int, int],
    graph: EnergyGraph,
    params: dict[str, str | float | int],
    *,
    seed: int,
    frame_index: int,
) -> Image.Image:
    """Build one coherent low/mid-energy body field with flowing painterly wisps."""
    rng = random.Random(seed * 130363 + frame_index * 10007 + 271)
    mask = Image.new("L", size, 0)
    phase = rng.uniform(0.0, math.tau)

    # Keep band energies close together. Geometry supplies width/offset while
    # core auras and scalar turbulence create brightness variation; this avoids
    # visible nested blue/cyan contour bands.
    band_specs = (
        (1.78, -0.24, 104),
        (1.52, 0.26, 112),
        (1.26, -0.06, 120),
        (0.92, 0.15, 128),
    )
    for index, (scale, shift, value) in enumerate(band_specs):
        points, widths = _mass_path(
            graph,
            params,
            rng,
            phase=phase + index * 1.17,
            normal_scale=scale,
            normal_shift=shift,
        )
        energy_value = round(value * (0.80 + 0.20 * graph.energy) * (1.0 - 0.20 * graph.breakup))
        _draw_variable_strip(mask, points, widths, energy_value)

    requested = int(params["shape.tongue_count"])
    span = min(1.0, max(0.0, (graph.head_t - graph.tail_t) / 0.50))
    wisp_count = max(0, round(requested * span * (0.70 + 0.30 * graph.energy) * (1.0 - 0.14 * graph.breakup)))
    length_control = float(params["shape.tongue_length"])
    curvature = float(params["shape.tongue_curve"])
    width_control = float(params["shape.tongue_width"])
    spread = max(0.25, float(params["lightning.spread"]))
    min_dim = min(size)
    usable_low = max(2, round(len(graph.nodes) * 0.04))
    usable_high = min(len(graph.nodes) - 3, round(len(graph.nodes) * 0.96))

    for index in range(wisp_count):
        slot_u = (index + rng.uniform(0.08, 0.92)) / max(1, wisp_count)
        node_index = round(usable_low + (usable_high - usable_low) * slot_u)
        node = graph.nodes[max(usable_low, min(usable_high, node_index))]
        length = min_dim * (0.045 + length_control * rng.uniform(0.115, 0.220))
        if index % 4 == 0:
            length *= rng.uniform(1.18, 1.52)
        points = _wisp_path(node, length=length, curvature=curvature, spread=spread, rng=rng)
        root_width = max(1.2, node.width * width_control * rng.uniform(0.66, 1.20))
        widths = _wisp_widths(root_width, len(points), rng)
        value = rng.randint(100, 132)
        if index % 5 == 0:
            value = rng.randint(120, 146)
        value = round(value * (0.80 + 0.20 * graph.energy))
        _draw_variable_strip(mask, points, widths, value)

    _draw_terminal_flows(mask, graph, params, rng)

    # Strong local smoothing plus a broad aura turns the line/strip collection
    # into one soft density field. Raw geometry is deliberately downweighted.
    soft = mask.filter(ImageFilter.GaussianBlur(5.0))
    wide = mask.filter(ImageFilter.GaussianBlur(12.0))
    width, height = size
    detail_amount = float(params["shape.detail_noise"])
    detail_frequency = float(params["shape.detail_noise_frequency"])
    noise_phase = (seed * 0.00137 + frame_index * 0.731) % math.tau
    result_values: list[int] = []
    for pixel_index, (raw, local, aura) in enumerate(zip(mask.getdata(), soft.getdata(), wide.getdata())):
        x = pixel_index % width
        y = pixel_index // width
        wave = (
            math.sin((x / width) * math.tau * detail_frequency * 0.22 + noise_phase) * 0.46
            + math.sin((y / height) * math.tau * detail_frequency * 0.16 - noise_phase * 0.71) * 0.31
            + math.sin(((x + y) / (width + height)) * math.tau * detail_frequency * 0.39 + noise_phase * 1.31) * 0.23
        )
        coherent_gain = 1.0 + wave * detail_amount * 0.30
        energy = max(raw * 0.42 + local * 0.58, local * 0.88, aura * 0.58)
        energy *= coherent_gain
        result_values.append(max(0, min(174, round(energy))))
    result = Image.new("L", size, 0)
    result.putdata(result_values)
    return result
