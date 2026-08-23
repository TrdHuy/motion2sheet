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
        local_value = max(0, min(255, round(value * (0.92 + 0.08 * (1.0 - index / max(1, len(points) - 1))))))
        draw.line([p0, p1], fill=local_value, width=width)
        radius = max(1, width // 2)
        for x, y in (p0, p1):
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=local_value)


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
        local_shift = normal_shift * node.width + coherent * form_noise * 4.2 * normal_scale
        points.append((
            node.point[0] + node.normal[0] * local_shift,
            node.point[1] + node.normal[1] * local_shift,
        ))
        target_noise = rng.uniform(-detail_noise * 0.12, detail_noise * 0.12)
        previous_width_noise = previous_width_noise * 0.72 + target_noise * 0.28
        envelope = _smoothstep01(u / 0.085) * _smoothstep01((1.0 - u) / 0.065)
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
) -> list[tuple[float, float]]:
    # Most wisps flow with the slash tangent; a minority trail backwards.
    tangent_sign = 1.0 if rng.random() > 0.18 else -1.0
    tx, ty = node.tangent[0] * tangent_sign, node.tangent[1] * tangent_sign
    nx, ny = node.normal
    normal_bias = rng.uniform(-0.24, 0.82) * spread
    dx, dy = normalize(tx + nx * normal_bias, ty + ny * normal_bias)
    px, py = -dy, dx
    root_depth = rng.uniform(-0.30, 0.20) * node.width
    root = (
        node.point[0] + node.normal[0] * root_depth,
        node.point[1] + node.normal[1] * root_depth,
    )
    count = rng.randint(7, 11)
    bend_sign = 1.0 if rng.random() > 0.5 else -1.0
    phase = rng.uniform(0.0, math.tau)
    frequency = rng.uniform(0.65, 1.15)
    points: list[tuple[float, float]] = []
    for index in range(count):
        u = index / (count - 1)
        advance = length * (u ** 0.90)
        bend = math.sin(math.pi * u) * length * curvature * 0.20 * bend_sign
        wave = math.sin(u * math.tau * frequency + phase) * length * 0.030 * (1.0 - u)
        points.append((
            root[0] + dx * advance + px * (bend + wave),
            root[1] + dy * advance + py * (bend + wave),
        ))
    return points


def _wisp_widths(root_width: float, count: int, rng: random.Random) -> list[float]:
    widths: list[float] = []
    local = 1.0
    for index in range(count):
        u = index / max(1, count - 1)
        local = local * 0.74 + rng.uniform(0.78, 1.18) * 0.26
        taper = (1.0 - u) ** 1.55
        widths.append(max(0.20, root_width * local * taper))
    widths[-1] = min(widths[-1], 0.22)
    return widths


def build_energy_mass_field(
    size: tuple[int, int],
    graph: EnergyGraph,
    params: dict[str, str | float | int],
    *,
    seed: int,
    frame_index: int,
) -> Image.Image:
    """Build low/mid-energy body mass and flowing wisps as one scalar field.

    The result intentionally contains *no color*. It is merged with the base,
    core and lightning fields before the shared blue→cyan→white mapping so
    every visual component belongs to the same energy/compositing model.
    """
    rng = random.Random(seed * 130363 + frame_index * 10007 + 271)
    mask = Image.new("L", size, 0)
    phase = rng.uniform(0.0, math.tau)

    # Several overlapping, offset bands break the single-ribbon silhouette.
    # Values stay below the cyan threshold so these layers remain blue after
    # the shared gradient mapping.
    band_specs = (
        (1.52, -0.18, 88),
        (1.30, 0.24, 104),
        (1.08, -0.04, 124),
        (0.78, 0.16, 142),
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
        energy_value = round(value * (0.76 + 0.24 * graph.energy) * (1.0 - 0.24 * graph.breakup))
        _draw_variable_strip(mask, points, widths, energy_value)

    requested = int(params["shape.tongue_count"])
    span = min(1.0, max(0.0, (graph.head_t - graph.tail_t) / 0.50))
    wisp_count = max(0, round(requested * span * (0.64 + 0.36 * graph.energy) * (1.0 - 0.18 * graph.breakup)))
    length_control = float(params["shape.tongue_length"])
    curvature = float(params["shape.tongue_curve"])
    width_control = float(params["shape.tongue_width"])
    spread = max(0.25, float(params["lightning.spread"]))
    min_dim = min(size)
    usable_low = max(2, round(len(graph.nodes) * 0.05))
    usable_high = min(len(graph.nodes) - 3, round(len(graph.nodes) * 0.95))

    for index in range(wisp_count):
        slot_u = (index + rng.uniform(0.08, 0.92)) / max(1, wisp_count)
        node_index = round(usable_low + (usable_high - usable_low) * slot_u)
        node = graph.nodes[max(usable_low, min(usable_high, node_index))]
        length = min_dim * (0.030 + length_control * rng.uniform(0.085, 0.165))
        if index % 4 == 0:
            length *= rng.uniform(1.18, 1.55)
        points = _wisp_path(node, length=length, curvature=curvature, spread=spread, rng=rng)
        root_width = max(0.9, node.width * width_control * rng.uniform(0.48, 0.98))
        widths = _wisp_widths(root_width, len(points), rng)
        value = rng.randint(88, 138)
        if index % 5 == 0:
            value = rng.randint(126, 154)
        value = round(value * (0.76 + 0.24 * graph.energy))
        _draw_variable_strip(mask, points, widths, value)

    # Diffuse just enough to unify overlapping bands/wisps into a painterly
    # energy mass while preserving long directional silhouettes.
    soft = mask.filter(ImageFilter.GaussianBlur(2.4))
    wide = mask.filter(ImageFilter.GaussianBlur(6.5))
    result_values: list[int] = []
    for raw, local, aura in zip(mask.getdata(), soft.getdata(), wide.getdata()):
        energy = max(raw, round(local * 0.86), round(aura * 0.42))
        result_values.append(max(0, min(176, energy)))
    result = Image.new("L", size, 0)
    result.putdata(result_values)
    return result
