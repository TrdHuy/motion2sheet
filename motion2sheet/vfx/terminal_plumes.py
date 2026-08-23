from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .energy_graph import EnergyGraph, EnergyNode, build_energy_graph, normalize, smoothstep01


def _hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def _mask_layer(mask: Image.Image, color: tuple[int, int, int], amount: float) -> Image.Image:
    alpha = mask.point(lambda value: max(0, min(255, round(value * amount))))
    layer = Image.new("RGBA", mask.size, (*color, 0))
    layer.putalpha(alpha)
    return layer


def _draw_path(mask: Image.Image, points: list[tuple[float, float]], widths: list[float], value: int, scale: int) -> None:
    if len(points) < 2:
        return
    draw = ImageDraw.Draw(mask)
    for index in range(len(points) - 1):
        p0 = (points[index][0] * scale, points[index][1] * scale)
        p1 = (points[index + 1][0] * scale, points[index + 1][1] * scale)
        width = max(1, round((widths[index] + widths[index + 1]) * 0.5 * scale))
        draw.line([p0, p1], fill=value, width=width)


def _plume_path(
    node: EnergyNode,
    direction_sign: float,
    *,
    length: float,
    normal_offset: float,
    tangent_bias: float,
    curvature: float,
    rng: random.Random,
) -> list[tuple[float, float]]:
    tx, ty = node.tangent[0] * direction_sign, node.tangent[1] * direction_sign
    nx, ny = node.normal
    dx, dy = normalize(tx + nx * tangent_bias, ty + ny * tangent_bias)
    px, py = -dy, dx
    root = (
        node.point[0] + node.normal[0] * node.width * normal_offset,
        node.point[1] + node.normal[1] * node.width * normal_offset,
    )
    count = 9
    phase = rng.uniform(0.0, math.tau)
    frequency = rng.uniform(0.75, 1.35)
    points: list[tuple[float, float]] = []
    for index in range(count):
        u = index / (count - 1)
        advance = length * (u ** 0.88)
        bend = math.sin(math.pi * u) * length * curvature
        wave = math.sin(u * math.tau * frequency + phase) * length * 0.012 * (1.0 - u)
        points.append((root[0] + dx * advance + px * (bend + wave), root[1] + dy * advance + py * (bend + wave)))
    return points


def _plume_widths(root_width: float, count: int, rng: random.Random, power: float) -> list[float]:
    result: list[float] = []
    local = 1.0
    for index in range(count):
        u = index / max(1, count - 1)
        local = local * 0.72 + rng.uniform(0.78, 1.20) * 0.28
        # Keep substantial width through the first half, then sharpen quickly.
        taper = max(0.0, 1.0 - u ** power)
        result.append(max(0.16, root_width * taper * local))
    result[-1] = 0.16
    return result


def _activity(graph: EnergyGraph) -> float:
    if graph.breakup > 0.0:
        return max(0.0, 1.0 - graph.breakup * 1.18)
    span = max(0.0, min(1.0, (graph.head_t - graph.tail_t) / 0.90))
    return smoothstep01(max(0.0, (span - 0.28) / 0.72))


def _render_plumes(
    graph: EnergyGraph,
    size: tuple[int, int],
    *,
    seed: int,
    frame_index: int,
) -> tuple[Image.Image, Image.Image, Image.Image]:
    scale = 3
    large = (size[0] * scale, size[1] * scale)
    blue = Image.new("L", large, 0)
    cyan = Image.new("L", large, 0)
    white = Image.new("L", large, 0)
    activity = _activity(graph)
    if activity <= 0.015:
        return (
            blue.resize(size, Image.Resampling.LANCZOS),
            cyan.resize(size, Image.Resampling.LANCZOS),
            white.resize(size, Image.Resampling.LANCZOS),
        )

    min_dim = min(size)
    endpoints = ((graph.nodes[-3], 1.0), (graph.nodes[2], -1.0))
    for endpoint_index, (node, direction_sign) in enumerate(endpoints):
        endpoint_rng = random.Random(seed * 104729 + frame_index * 7919 + endpoint_index * 1009 + 701)
        for tier, count in ((0, 6), (1, 4), (2, 2)):
            target = blue if tier == 0 else cyan if tier == 1 else white
            for plume_index in range(count):
                rng = random.Random(endpoint_rng.randrange(1 << 30) + tier * 991 + plume_index * 313)
                if tier == 0:
                    length = min_dim * rng.uniform(0.20, 0.38) * activity
                    root_width = max(1.5, node.width * rng.uniform(0.32, 0.68) * activity)
                    normal_offset = rng.uniform(0.15, 1.10)
                    tangent_bias = rng.uniform(-0.12, 0.22)
                    curvature = rng.uniform(-0.050, 0.050)
                    value = round(rng.randint(105, 165) * activity)
                    power = rng.uniform(1.55, 2.10)
                elif tier == 1:
                    length = min_dim * rng.uniform(0.18, 0.34) * activity
                    root_width = max(1.1, node.width * rng.uniform(0.20, 0.44) * activity)
                    normal_offset = rng.uniform(-0.05, 0.62)
                    tangent_bias = rng.uniform(-0.10, 0.16)
                    curvature = rng.uniform(-0.040, 0.040)
                    value = round(rng.randint(135, 195) * activity)
                    power = rng.uniform(1.65, 2.25)
                else:
                    length = min_dim * rng.uniform(0.15, 0.30) * activity
                    root_width = max(0.8, node.width * rng.uniform(0.10, 0.22) * activity)
                    normal_offset = rng.uniform(-0.34, 0.02)
                    tangent_bias = rng.uniform(-0.08, 0.10)
                    curvature = rng.uniform(-0.028, 0.028)
                    value = round(rng.randint(155, 215) * activity)
                    power = rng.uniform(1.80, 2.35)
                path = _plume_path(
                    node,
                    direction_sign,
                    length=length,
                    normal_offset=normal_offset,
                    tangent_bias=tangent_bias,
                    curvature=curvature,
                    rng=rng,
                )
                widths = _plume_widths(root_width, len(path), rng, power)
                _draw_path(target, path, widths, value, scale)

    return (
        blue.resize(size, Image.Resampling.LANCZOS),
        cyan.resize(size, Image.Resampling.LANCZOS),
        white.resize(size, Image.Resampling.LANCZOS),
    )


def add_terminal_plumes(
    frame: Image.Image,
    params: dict[str, str | float | int],
    *,
    seed: int,
    frame_index: int,
    frame_count: int,
) -> Image.Image:
    graph = build_energy_graph(frame.size, params, seed=seed, frame_index=frame_index, frame_count=frame_count)
    blue, cyan, white = _render_plumes(graph, frame.size, seed=seed, frame_index=frame_index)
    outer = _hex_rgb(str(params["colors.outer"]))
    body = _hex_rgb(str(params["colors.body"]))
    inner = _hex_rgb(str(params["colors.inner"]))
    core = _hex_rgb(str(params["colors.core"]))
    result = frame.convert("RGBA")
    result = Image.alpha_composite(result, _mask_layer(blue.filter(ImageFilter.GaussianBlur(7.0)), outer, 0.20))
    result = Image.alpha_composite(result, _mask_layer(blue.filter(ImageFilter.GaussianBlur(0.55)), body, 0.66))
    result = Image.alpha_composite(result, _mask_layer(cyan.filter(ImageFilter.GaussianBlur(4.0)), inner, 0.20))
    result = Image.alpha_composite(result, _mask_layer(cyan.filter(ImageFilter.GaussianBlur(0.45)), inner, 0.64))
    result = Image.alpha_composite(result, _mask_layer(white.filter(ImageFilter.GaussianBlur(2.5)), inner, 0.22))
    result = Image.alpha_composite(result, _mask_layer(white.filter(ImageFilter.GaussianBlur(0.40)), core, 0.58))
    return result


def apply_terminal_plumes_to_frames(
    frame_paths: list[Path],
    params: dict[str, str | float | int],
    *,
    seed: int,
) -> None:
    frame_count = len(frame_paths)
    for frame_index, frame_path in enumerate(frame_paths):
        frame = Image.open(frame_path).convert("RGBA")
        add_terminal_plumes(
            frame,
            params,
            seed=seed,
            frame_index=frame_index,
            frame_count=frame_count,
        ).save(frame_path)
