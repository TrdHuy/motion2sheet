from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .energy_graph import EnergyGraph, EnergyNode, build_energy_graph, normalize


def _hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def _smoothstep01(value: float) -> float:
    x = max(0.0, min(1.0, value))
    return x * x * (3.0 - 2.0 * x)


def _draw_tapered_strip(
    overlay: Image.Image,
    points: list[tuple[float, float]],
    widths: list[float],
    color: tuple[int, int, int, int],
    *,
    supersample: int = 2,
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
        tx, ty = normalize(following[0] - previous[0], following[1] - previous[1])
        nx, ny = -ty, tx
        half = max(0.08, width * 0.5)
        left.append(((x + nx * half) * scale, (y + ny * half) * scale))
        right.append(((x - nx * half) * scale, (y - ny * half) * scale))
    ImageDraw.Draw(large, "RGBA").polygon(left + list(reversed(right)), fill=color)
    if scale > 1:
        large = large.resize(overlay.size, Image.Resampling.LANCZOS)
    overlay.alpha_composite(large)


def _mass_path(
    graph: EnergyGraph,
    params: dict[str, str | float | int],
    rng: random.Random,
    *,
    phase: float,
    normal_scale: float,
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
        offset = coherent * form_noise * 4.2 * normal_scale
        points.append((node.point[0] + node.normal[0] * offset, node.point[1] + node.normal[1] * offset))
        target_noise = rng.uniform(-detail_noise * 0.11, detail_noise * 0.11)
        previous_width_noise = previous_width_noise * 0.70 + target_noise * 0.30
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
    tangent_sign = 1.0 if rng.random() > 0.20 else -1.0
    tx, ty = node.tangent[0] * tangent_sign, node.tangent[1] * tangent_sign
    nx, ny = node.normal
    normal_bias = rng.uniform(-0.18, 0.82) * spread
    dx, dy = normalize(tx + nx * normal_bias, ty + ny * normal_bias)
    px, py = -dy, dx
    root = (
        node.point[0] - node.normal[0] * node.width * rng.uniform(0.05, 0.32),
        node.point[1] - node.normal[1] * node.width * rng.uniform(0.05, 0.32),
    )
    count = rng.randint(6, 9)
    bend_sign = 1.0 if rng.random() > 0.5 else -1.0
    phase = rng.uniform(0.0, math.tau)
    points: list[tuple[float, float]] = []
    for index in range(count):
        u = index / (count - 1)
        advance = length * (u ** 0.92)
        bend = math.sin(math.pi * u) * length * curvature * 0.22 * bend_sign
        wave = math.sin(u * math.tau * rng.uniform(0.65, 1.20) + phase) * length * 0.035 * (1.0 - u)
        points.append((root[0] + dx * advance + px * (bend + wave), root[1] + dy * advance + py * (bend + wave)))
    return points


def _wisp_widths(root_width: float, count: int, rng: random.Random) -> list[float]:
    widths: list[float] = []
    local = 1.0
    for index in range(count):
        u = index / max(1, count - 1)
        local = local * 0.72 + rng.uniform(0.78, 1.18) * 0.28
        taper = (1.0 - u) ** 1.45
        widths.append(max(0.18, root_width * local * taper))
    widths[-1] = min(widths[-1], 0.24)
    return widths


def _build_energy_underlay(
    size: tuple[int, int],
    graph: EnergyGraph,
    params: dict[str, str | float | int],
    *,
    seed: int,
    frame_index: int,
) -> Image.Image:
    rng = random.Random(seed * 130363 + frame_index * 10007 + 271)
    outer_rgb = _hex_rgb(str(params["colors.outer"]))
    body_rgb = _hex_rgb(str(params["colors.body"]))
    inner_rgb = _hex_rgb(str(params["colors.inner"]))
    underlay = Image.new("RGBA", size, (0, 0, 0, 0))

    phase = rng.uniform(0.0, math.tau)
    outer_points, outer_widths = _mass_path(graph, params, rng, phase=phase, normal_scale=1.34)
    body_points, body_widths = _mass_path(graph, params, rng, phase=phase + 1.73, normal_scale=1.00)
    inner_points, inner_widths = _mass_path(graph, params, rng, phase=phase - 0.91, normal_scale=0.54)

    mass_alpha = round(108 * (0.72 + 0.28 * graph.energy) * (1.0 - 0.28 * graph.breakup))
    _draw_tapered_strip(underlay, outer_points, outer_widths, (*outer_rgb, max(30, mass_alpha - 28)), supersample=2)
    _draw_tapered_strip(underlay, body_points, body_widths, (*body_rgb, mass_alpha), supersample=2)
    _draw_tapered_strip(underlay, inner_points, inner_widths, (*inner_rgb, max(24, mass_alpha // 3)), supersample=2)

    requested = int(params["shape.tongue_count"])
    span = min(1.0, max(0.0, (graph.head_t - graph.tail_t) / 0.50))
    wisp_count = max(0, round(requested * span * (0.58 + 0.42 * graph.energy) * (1.0 - 0.25 * graph.breakup)))
    length_control = float(params["shape.tongue_length"])
    curvature = float(params["shape.tongue_curve"])
    width_control = float(params["shape.tongue_width"])
    spread = max(0.25, float(params["lightning.spread"]))
    min_dim = min(size)
    usable_low = max(2, round(len(graph.nodes) * 0.06))
    usable_high = min(len(graph.nodes) - 3, round(len(graph.nodes) * 0.94))

    for index in range(wisp_count):
        slot_u = (index + rng.uniform(0.12, 0.88)) / max(1, wisp_count)
        node_index = round(usable_low + (usable_high - usable_low) * slot_u)
        node = graph.nodes[max(usable_low, min(usable_high, node_index))]
        length = min_dim * (0.035 + length_control * rng.uniform(0.075, 0.145))
        if index % 5 == 0:
            length *= rng.uniform(1.18, 1.48)
        points = _wisp_path(node, length=length, curvature=curvature, spread=spread, rng=rng)
        root_width = max(0.8, node.width * width_control * rng.uniform(0.42, 0.90))
        widths = _wisp_widths(root_width, len(points), rng)
        alpha = round(rng.uniform(62, 116) * (0.70 + 0.30 * graph.energy))
        color = body_rgb if index % 4 else inner_rgb
        _draw_tapered_strip(underlay, points, widths, (*color, alpha), supersample=3)
        if index % 3 == 0:
            _draw_tapered_strip(
                underlay,
                points,
                [max(0.12, width * 0.34) for width in widths],
                (*inner_rgb, max(24, alpha // 3)),
                supersample=3,
            )

    # A soft royal-blue aura makes the body read as one turbulent energy mass
    # rather than as isolated strips, while preserving the high-energy core on top.
    aura_alpha = underlay.getchannel("A").filter(ImageFilter.GaussianBlur(6.0))
    aura_alpha = aura_alpha.point(lambda value: round(value * 0.34))
    aura = Image.new("RGBA", size, (*outer_rgb, 0))
    aura.putalpha(aura_alpha)
    return Image.alpha_composite(aura, underlay)


def apply_energy_mass(
    frame: Image.Image,
    params: dict[str, str | float | int],
    *,
    seed: int,
    frame_index: int,
    frame_count: int,
) -> Image.Image:
    graph = build_energy_graph(frame.size, params, seed=seed, frame_index=frame_index, frame_count=frame_count)
    if graph.head_t - graph.tail_t <= 0.025:
        return frame
    underlay = _build_energy_underlay(frame.size, graph, params, seed=seed, frame_index=frame_index)
    return Image.alpha_composite(underlay, frame.convert("RGBA"))


def apply_energy_mass_to_frames(
    frame_paths: list[Path],
    params: dict[str, str | float | int],
    *,
    seed: int,
) -> None:
    frame_count = len(frame_paths)
    for frame_index, frame_path in enumerate(frame_paths):
        frame = Image.open(frame_path).convert("RGBA")
        apply_energy_mass(
            frame,
            params,
            seed=seed,
            frame_index=frame_index,
            frame_count=frame_count,
        ).save(frame_path)
