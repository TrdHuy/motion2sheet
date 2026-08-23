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


def _activity(graph: EnergyGraph) -> float:
    if graph.breakup > 0.0:
        return max(0.0, 1.0 - graph.breakup * 0.92)
    span = max(0.0, min(1.0, (graph.head_t - graph.tail_t) / 0.90))
    return smoothstep01(span)


def _inner_path(node: EnergyNode, direction_sign: float, length: float, rng: random.Random) -> list[tuple[float, float]]:
    tx, ty = node.tangent[0] * direction_sign, node.tangent[1] * direction_sign
    nx, ny = -node.normal[0], -node.normal[1]
    direction = normalize(tx + nx * rng.uniform(0.05, 0.42), ty + ny * rng.uniform(0.05, 0.42))
    dx, dy = direction
    px, py = -dy, dx
    root_offset = rng.uniform(0.08, 0.55)
    root = (node.point[0] - node.normal[0] * node.width * root_offset, node.point[1] - node.normal[1] * node.width * root_offset)
    phase = rng.uniform(0.0, math.tau)
    curvature = rng.uniform(-0.045, 0.045)
    points: list[tuple[float, float]] = []
    count = rng.randint(7, 10)
    for index in range(count):
        u = index / (count - 1)
        advance = length * (u ** 0.90)
        bend = math.sin(math.pi * u) * length * curvature
        wave = math.sin(u * math.tau * rng.uniform(0.75, 1.25) + phase) * length * 0.014 * (1.0 - u)
        points.append((root[0] + dx * advance + px * (bend + wave), root[1] + dy * advance + py * (bend + wave)))
    return points


def _taper(root_width: float, count: int, rng: random.Random) -> list[float]:
    values: list[float] = []
    local = 1.0
    for index in range(count):
        u = index / max(1, count - 1)
        local = local * 0.72 + rng.uniform(0.78, 1.20) * 0.28
        values.append(max(0.14, root_width * local * ((1.0 - u) ** 1.55)))
    values[-1] = 0.14
    return values


def _render_inner_wisps(
    graph: EnergyGraph,
    size: tuple[int, int],
    *,
    seed: int,
    frame_index: int,
) -> tuple[Image.Image, Image.Image]:
    scale = 3
    large = (size[0] * scale, size[1] * scale)
    blue = Image.new("L", large, 0)
    cyan = Image.new("L", large, 0)
    activity = _activity(graph)
    if activity < 0.05:
        return blue.resize(size, Image.Resampling.LANCZOS), cyan.resize(size, Image.Resampling.LANCZOS)
    rng = random.Random(seed * 3145739 + frame_index * 12289 + 911)
    min_dim = min(size)
    blue_count = round(12 * activity)
    cyan_count = round(6 * activity)
    for tier, count, target in ((0, blue_count, blue), (1, cyan_count, cyan)):
        for index in range(count):
            life_rng = random.Random(seed * 99991 + tier * 1709 + index * 811)
            death = life_rng.uniform(0.42 if tier == 0 else 0.54, 1.06)
            if graph.breakup > death:
                continue
            slot = (index + rng.uniform(0.12, 0.88)) / max(1, count)
            node_index = max(5, min(len(graph.nodes) - 6, round(5 + slot * (len(graph.nodes) - 11))))
            node = graph.nodes[node_index]
            direction_sign = 1.0 if rng.random() < 0.72 else -1.0
            if tier == 0:
                length = min_dim * rng.uniform(0.065, 0.180) * activity
                root_width = max(1.0, node.width * rng.uniform(0.10, 0.24) * activity)
                value = rng.randint(95, 150)
            else:
                length = min_dim * rng.uniform(0.050, 0.145) * activity
                root_width = max(0.7, node.width * rng.uniform(0.07, 0.17) * activity)
                value = rng.randint(125, 180)
            path = _inner_path(node, direction_sign, length, rng)
            widths = _taper(root_width, len(path), rng)
            _draw_path(target, path, widths, value, scale)
    return blue.resize(size, Image.Resampling.LANCZOS), cyan.resize(size, Image.Resampling.LANCZOS)


def _bright_mask(frame: Image.Image) -> Image.Image:
    rgba = frame.convert("RGBA")
    values: list[int] = []
    for r, g, b, a in rgba.getdata():
        if a <= 4:
            values.append(0)
            continue
        brightness = max(r, g, b) / 255.0
        cyan_bias = min(1.0, (g + b) / 390.0)
        white_bias = min(1.0, (r + g + b) / 650.0)
        energy = max(0.0, brightness * 0.45 + cyan_bias * 0.30 + white_bias * 0.25 - 0.28)
        values.append(round(255 * energy * (a / 255.0)))
    mask = Image.new("L", rgba.size, 0)
    mask.putdata(values)
    return mask


def add_plasma_finish(
    frame: Image.Image,
    params: dict[str, str | float | int],
    *,
    seed: int,
    frame_index: int,
    frame_count: int,
) -> Image.Image:
    graph = build_energy_graph(frame.size, params, seed=seed, frame_index=frame_index, frame_count=frame_count)
    blue_wisps, cyan_wisps = _render_inner_wisps(graph, frame.size, seed=seed, frame_index=frame_index)
    outer = _hex_rgb(str(params["colors.outer"]))
    body = _hex_rgb(str(params["colors.body"]))
    inner = _hex_rgb(str(params["colors.inner"]))

    result = frame.convert("RGBA")
    result = Image.alpha_composite(result, _mask_layer(blue_wisps.filter(ImageFilter.GaussianBlur(4.8)), body, 0.22))
    result = Image.alpha_composite(result, _mask_layer(blue_wisps.filter(ImageFilter.GaussianBlur(0.38)), body, 0.62))
    result = Image.alpha_composite(result, _mask_layer(cyan_wisps.filter(ImageFilter.GaussianBlur(3.2)), inner, 0.22))
    result = Image.alpha_composite(result, _mask_layer(cyan_wisps.filter(ImageFilter.GaussianBlur(0.34)), inner, 0.58))

    # Build the aura from final sparse stroke occupancy. This enlarges the soft
    # energy field without reintroducing a filled geometric crescent mask.
    alpha = result.getchannel("A")
    bright = _bright_mask(result)
    outer_wide = alpha.filter(ImageFilter.GaussianBlur(18.0))
    outer_mid = alpha.filter(ImageFilter.GaussianBlur(9.0))
    bright_wide = bright.filter(ImageFilter.GaussianBlur(10.0))
    bright_tight = bright.filter(ImageFilter.GaussianBlur(4.5))
    under = Image.new("RGBA", result.size, (0, 0, 0, 0))
    under = Image.alpha_composite(under, _mask_layer(outer_wide, outer, 0.15))
    under = Image.alpha_composite(under, _mask_layer(outer_mid, body, 0.16))
    under = Image.alpha_composite(under, _mask_layer(bright_wide, body, 0.18))
    under = Image.alpha_composite(under, _mask_layer(bright_tight, inner, 0.20))
    return Image.alpha_composite(under, result)


def apply_plasma_finish_to_frames(
    frame_paths: list[Path],
    params: dict[str, str | float | int],
    *,
    seed: int,
) -> None:
    frame_count = len(frame_paths)
    for frame_index, frame_path in enumerate(frame_paths):
        frame = Image.open(frame_path).convert("RGBA")
        add_plasma_finish(
            frame,
            params,
            seed=seed,
            frame_index=frame_index,
            frame_count=frame_count,
        ).save(frame_path)
