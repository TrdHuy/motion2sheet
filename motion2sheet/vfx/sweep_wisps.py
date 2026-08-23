from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .energy_graph import EnergyGraph, EnergyNode, build_energy_graph, normalize


def _hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def _mask_layer(mask: Image.Image, color: tuple[int, int, int], amount: float) -> Image.Image:
    alpha = mask.point(lambda value: max(0, min(255, round(value * amount))))
    layer = Image.new("RGBA", mask.size, (*color, 0))
    layer.putalpha(alpha)
    return layer


def _draw_variable_line(
    mask: Image.Image,
    points: list[tuple[float, float]],
    widths: list[float],
    value: int,
    *,
    scale: int,
) -> None:
    if len(points) < 2:
        return
    draw = ImageDraw.Draw(mask)
    for index in range(len(points) - 1):
        p0 = (points[index][0] * scale, points[index][1] * scale)
        p1 = (points[index + 1][0] * scale, points[index + 1][1] * scale)
        width = max(1, round((widths[index] + widths[index + 1]) * 0.5 * scale))
        draw.line([p0, p1], fill=value, width=width)


def _sweep_path(
    node: EnergyNode,
    *,
    direction_sign: float,
    length: float,
    outward_bias: float,
    curvature: float,
    rng: random.Random,
) -> list[tuple[float, float]]:
    tx, ty = node.tangent[0] * direction_sign, node.tangent[1] * direction_sign
    nx, ny = node.normal
    dx, dy = normalize(tx + nx * outward_bias, ty + ny * outward_bias)
    px, py = -dy, dx
    count = rng.randint(7, 10)
    phase = rng.uniform(0.0, math.tau)
    bend_sign = 1.0 if rng.random() > 0.5 else -1.0
    points: list[tuple[float, float]] = []
    root = (
        node.point[0] + node.normal[0] * node.width * rng.uniform(-0.08, 0.72),
        node.point[1] + node.normal[1] * node.width * rng.uniform(-0.08, 0.72),
    )
    for index in range(count):
        u = index / (count - 1)
        advance = length * (u ** 0.90)
        bend = math.sin(math.pi * u) * length * curvature * bend_sign
        wave = math.sin(u * math.tau * rng.uniform(0.70, 1.30) + phase) * length * 0.018 * (1.0 - u)
        points.append((root[0] + dx * advance + px * (bend + wave), root[1] + dy * advance + py * (bend + wave)))
    return points


def _taper_widths(root_width: float, count: int, rng: random.Random, *, power: float = 1.55) -> list[float]:
    widths: list[float] = []
    local = 1.0
    for index in range(count):
        u = index / max(1, count - 1)
        local = local * 0.70 + rng.uniform(0.76, 1.22) * 0.30
        widths.append(max(0.14, root_width * local * ((1.0 - u) ** power)))
    widths[-1] = min(widths[-1], 0.18)
    return widths


def _survival(seed: int, tier: int, index: int, breakup: float) -> tuple[bool, float]:
    rng = random.Random(seed * 29791 + tier * 1009 + index * 811)
    death = rng.uniform(0.36 if tier == 0 else 0.48, 1.10 if tier == 0 else 1.16)
    if breakup <= death:
        return True, 1.0
    excess = (breakup - death) / max(0.04, 1.0 - min(0.98, death))
    return excess < 0.88, max(0.18, 1.0 - excess * 0.78)


def _render_wisp_masks(
    graph: EnergyGraph,
    size: tuple[int, int],
    params: dict[str, str | float | int],
    *,
    seed: int,
    frame_index: int,
) -> tuple[Image.Image, Image.Image, Image.Image]:
    scale = 3
    large = (size[0] * scale, size[1] * scale)
    blue = Image.new("L", large, 0)
    cyan = Image.new("L", large, 0)
    hot = Image.new("L", large, 0)
    min_dim = min(size)
    span = max(0.0, min(1.0, (graph.head_t - graph.tail_t) / 0.50))
    rng = random.Random(seed * 786433 + frame_index * 8191 + 3181)

    blue_count = max(10, min(18, round(int(params["shape.tongue_count"]) * 0.40 * (0.62 + 0.38 * span))))
    cyan_count = max(5, min(10, round(blue_count * 0.48)))
    usable_low = 3
    usable_high = len(graph.nodes) - 4

    for tier, count, mask in ((0, blue_count, blue), (1, cyan_count, cyan)):
        for index in range(count):
            alive, opacity = _survival(seed, tier, index, graph.breakup)
            if not alive:
                continue
            slot = (index + rng.uniform(0.10, 0.90)) / max(1, count)
            node_index = round(usable_low + (usable_high - usable_low) * slot)
            node = graph.nodes[max(usable_low, min(usable_high, node_index))]
            direction_sign = 1.0 if rng.random() < 0.72 else -1.0
            if tier == 0:
                length = min_dim * rng.uniform(0.085, 0.245) * (0.72 + 0.28 * graph.energy)
                root_width = max(1.2, node.width * rng.uniform(0.10, 0.24))
                outward_bias = rng.uniform(0.04, 0.34)
                curvature = rng.uniform(-0.055, 0.055)
                value = round(150 * opacity)
            else:
                length = min_dim * rng.uniform(0.065, 0.190) * (0.75 + 0.25 * graph.energy)
                root_width = max(0.9, node.width * rng.uniform(0.07, 0.16))
                outward_bias = rng.uniform(-0.02, 0.24)
                curvature = rng.uniform(-0.045, 0.045)
                value = round(184 * opacity)
            path = _sweep_path(
                node,
                direction_sign=direction_sign,
                length=length,
                outward_bias=outward_bias,
                curvature=curvature,
                rng=rng,
            )
            widths = _taper_widths(root_width, len(path), rng)
            _draw_variable_line(mask, path, widths, value, scale=scale)

    # Peak hot streaks are the long directional cutting plumes visible in the
    # approved contract. Their roots remain embedded in the core and taper to
    # sharp tips; they fade/fragment naturally after the peak.
    if graph.energy > 0.64 and graph.breakup < 0.78:
        for terminal_index, (node, direction_sign) in enumerate(((graph.nodes[-3], 1.0), (graph.nodes[2], -1.0))):
            local_rng = random.Random(seed * 16127 + frame_index * 997 + terminal_index * 101)
            life = max(0.0, 1.0 - graph.breakup * (1.15 + terminal_index * 0.12))
            length = min_dim * local_rng.uniform(0.20, 0.38) * (0.82 + 0.18 * graph.energy) * max(0.32, life)
            path = _sweep_path(
                node,
                direction_sign=direction_sign,
                length=length,
                outward_bias=local_rng.uniform(-0.08, 0.12),
                curvature=local_rng.uniform(-0.035, 0.035),
                rng=local_rng,
            )
            root_width = max(2.0, node.width * local_rng.uniform(0.18, 0.32))
            widths = _taper_widths(root_width, len(path), local_rng, power=1.35)
            _draw_variable_line(hot, path, widths, round(230 * max(0.40, life)), scale=scale)

    return (
        blue.resize(size, Image.Resampling.LANCZOS),
        cyan.resize(size, Image.Resampling.LANCZOS),
        hot.resize(size, Image.Resampling.LANCZOS),
    )


def _ignition_burst(
    frame: Image.Image,
    graph: EnergyGraph,
    params: dict[str, str | float | int],
    *,
    seed: int,
    frame_index: int,
) -> Image.Image:
    span = graph.head_t - graph.tail_t
    if span > 0.28:
        return frame
    rng = random.Random(seed * 131071 + frame_index * 1709 + 41)
    center = graph.nodes[len(graph.nodes) // 2].point
    inner = _hex_rgb(str(params["colors.inner"]))
    core = _hex_rgb(str(params["colors.core"]))
    blue = _hex_rgb(str(params["colors.body"]))
    blue_mask = Image.new("L", frame.size, 0)
    cyan_mask = Image.new("L", frame.size, 0)
    hot_mask = Image.new("L", frame.size, 0)
    blue_draw = ImageDraw.Draw(blue_mask)
    cyan_draw = ImageDraw.Draw(cyan_mask)
    hot_draw = ImageDraw.Draw(hot_mask)
    ray_count = 12
    for index in range(ray_count):
        angle = math.tau * index / ray_count + rng.uniform(-0.13, 0.13)
        length = min(frame.size) * rng.uniform(0.035, 0.13)
        end = (center[0] + math.cos(angle) * length, center[1] + math.sin(angle) * length)
        blue_draw.line([center, end], fill=rng.randint(95, 165), width=rng.randint(2, 5))
        if index % 2 == 0:
            cyan_draw.line([center, end], fill=rng.randint(140, 215), width=rng.randint(1, 3))
        if index % 4 == 0:
            hot_draw.line([center, end], fill=220, width=1)
    result = Image.alpha_composite(frame, _mask_layer(blue_mask.filter(ImageFilter.GaussianBlur(2.8)), blue, 0.52))
    result = Image.alpha_composite(result, _mask_layer(cyan_mask.filter(ImageFilter.GaussianBlur(1.4)), inner, 0.72))
    return Image.alpha_composite(result, _mask_layer(hot_mask.filter(ImageFilter.GaussianBlur(0.45)), core, 0.78))


def add_sweep_wisps(
    frame: Image.Image,
    params: dict[str, str | float | int],
    *,
    seed: int,
    frame_index: int,
    frame_count: int,
) -> Image.Image:
    graph = build_energy_graph(frame.size, params, seed=seed, frame_index=frame_index, frame_count=frame_count)
    blue_mask, cyan_mask, hot_mask = _render_wisp_masks(
        graph,
        frame.size,
        params,
        seed=seed,
        frame_index=frame_index,
    )
    outer = _hex_rgb(str(params["colors.outer"]))
    body = _hex_rgb(str(params["colors.body"]))
    inner = _hex_rgb(str(params["colors.inner"]))
    core = _hex_rgb(str(params["colors.core"]))

    result = frame.convert("RGBA")
    result = Image.alpha_composite(result, _mask_layer(blue_mask.filter(ImageFilter.GaussianBlur(5.5)), outer, 0.18))
    result = Image.alpha_composite(result, _mask_layer(blue_mask.filter(ImageFilter.GaussianBlur(0.35)), body, 0.78))
    result = Image.alpha_composite(result, _mask_layer(cyan_mask.filter(ImageFilter.GaussianBlur(2.8)), inner, 0.18))
    result = Image.alpha_composite(result, _mask_layer(cyan_mask.filter(ImageFilter.GaussianBlur(0.28)), inner, 0.74))
    result = Image.alpha_composite(result, _mask_layer(hot_mask.filter(ImageFilter.GaussianBlur(2.4)), inner, 0.24))
    result = Image.alpha_composite(result, _mask_layer(hot_mask.filter(ImageFilter.GaussianBlur(0.26)), core, 0.80))
    return _ignition_burst(result, graph, params, seed=seed, frame_index=frame_index)


def apply_sweep_wisps_to_frames(
    frame_paths: list[Path],
    params: dict[str, str | float | int],
    *,
    seed: int,
) -> None:
    frame_count = len(frame_paths)
    for frame_index, frame_path in enumerate(frame_paths):
        frame = Image.open(frame_path).convert("RGBA")
        add_sweep_wisps(
            frame,
            params,
            seed=seed,
            frame_index=frame_index,
            frame_count=frame_count,
        ).save(frame_path)
