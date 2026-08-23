from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .energy_graph import EnergyGraph, EnergyNode, build_energy_graph, normalize, smoothstep01


def _hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def _mask_layer(mask: Image.Image, color: tuple[int, int, int], amount: float) -> Image.Image:
    alpha = mask.point(lambda value: max(0, min(255, round(value * amount))))
    layer = Image.new("RGBA", mask.size, (*color, 0))
    layer.putalpha(alpha)
    return layer


def _activity(graph: EnergyGraph) -> float:
    if graph.breakup > 0.55:
        return 0.0
    if graph.breakup > 0.0:
        return max(0.0, 1.0 - graph.breakup * 1.45)
    span = max(0.0, min(1.0, (graph.head_t - graph.tail_t) / 0.90))
    return smoothstep01(span)


def _body_support(frame: Image.Image) -> Image.Image:
    """Return only established blue body pixels; cyan/white energy is protected."""
    rgba = frame.convert("RGBA")
    values: list[int] = []
    for r, g, b, a in rgba.getdata():
        if a < 72 or b < 128:
            values.append(0)
            continue
        if g > b * 0.68 or r > max(70, g * 0.72):
            values.append(0)
            continue
        values.append(min(255, round(a * 1.12)))
    support = Image.new("L", rgba.size, 0)
    support.putdata(values)
    return support.filter(ImageFilter.MinFilter(5))


def _texture_path(
    node: EnergyNode,
    *,
    length: float,
    outward: float,
    direction_sign: float,
    rng: random.Random,
) -> list[tuple[float, float]]:
    tx, ty = node.tangent[0] * direction_sign, node.tangent[1] * direction_sign
    nx, ny = node.normal
    direction = normalize(tx + nx * rng.uniform(-0.10, 0.12), ty + ny * rng.uniform(-0.10, 0.12))
    dx, dy = direction
    px, py = -dy, dx
    root = (
        node.point[0] + nx * node.width * outward + tx * node.width * rng.uniform(-0.16, 0.16),
        node.point[1] + ny * node.width * outward + ty * node.width * rng.uniform(-0.16, 0.16),
    )
    phase = rng.uniform(0.0, math.tau)
    points: list[tuple[float, float]] = []
    count = rng.randint(5, 8)
    for index in range(count):
        u = index / max(1, count - 1)
        advance = length * u
        wave = math.sin(u * math.tau * rng.uniform(0.70, 1.20) + phase) * length * 0.026 * (1.0 - u)
        bend = math.sin(math.pi * u) * length * rng.uniform(-0.018, 0.018)
        points.append((root[0] + dx * advance + px * (wave + bend), root[1] + dy * advance + py * (wave + bend)))
    return points


def _draw_tapered(mask: Image.Image, points: list[tuple[float, float]], root_width: float, value: int, scale: int) -> None:
    if len(points) < 2:
        return
    draw = ImageDraw.Draw(mask)
    for index in range(len(points) - 1):
        u = index / max(1, len(points) - 2)
        width = max(1, round(root_width * ((1.0 - u) ** 1.45) * scale))
        p0 = (points[index][0] * scale, points[index][1] * scale)
        p1 = (points[index + 1][0] * scale, points[index + 1][1] * scale)
        draw.line([p0, p1], fill=value, width=width)


def _render_texture_masks(
    graph: EnergyGraph,
    size: tuple[int, int],
    *,
    seed: int,
    frame_index: int,
) -> tuple[Image.Image, Image.Image]:
    scale = 3
    large = (size[0] * scale, size[1] * scale)
    holes = Image.new("L", large, 0)
    cyan = Image.new("L", large, 0)
    activity = _activity(graph)
    if activity < 0.18:
        return holes.resize(size, Image.Resampling.LANCZOS), cyan.resize(size, Image.Resampling.LANCZOS)

    rng = random.Random(seed * 433494437 + frame_index * 13007 + 271)
    min_dim = min(size)
    hole_count = max(3, round(14 * activity))
    cyan_count = max(2, round(9 * activity))

    for _ in range(hole_count):
        node = graph.nodes[rng.randint(5, len(graph.nodes) - 6)]
        length = min_dim * rng.uniform(0.032, 0.095) * activity
        path = _texture_path(
            node,
            length=length,
            outward=rng.uniform(0.30, 1.18),
            direction_sign=1.0 if rng.random() < 0.72 else -1.0,
            rng=rng,
        )
        _draw_tapered(
            holes,
            path,
            root_width=max(0.8, node.width * rng.uniform(0.070, 0.150)),
            value=rng.randint(125, 185),
            scale=scale,
        )

    for _ in range(cyan_count):
        node = graph.nodes[rng.randint(5, len(graph.nodes) - 6)]
        length = min_dim * rng.uniform(0.040, 0.110) * activity
        path = _texture_path(
            node,
            length=length,
            outward=rng.uniform(0.22, 0.96),
            direction_sign=1.0 if rng.random() < 0.78 else -1.0,
            rng=rng,
        )
        _draw_tapered(
            cyan,
            path,
            root_width=max(0.65, node.width * rng.uniform(0.050, 0.105)),
            value=rng.randint(120, 170),
            scale=scale,
        )

    return holes.resize(size, Image.Resampling.LANCZOS), cyan.resize(size, Image.Resampling.LANCZOS)


def add_body_texture(
    frame: Image.Image,
    params: dict[str, str | float | int],
    *,
    seed: int,
    frame_index: int,
    frame_count: int,
) -> Image.Image:
    graph = build_energy_graph(frame.size, params, seed=seed, frame_index=frame_index, frame_count=frame_count)
    support = _body_support(frame)
    holes, cyan = _render_texture_masks(graph, frame.size, seed=seed, frame_index=frame_index)
    holes = ImageChops.multiply(holes.filter(ImageFilter.GaussianBlur(0.55)), support)
    cyan_sharp = ImageChops.multiply(cyan.filter(ImageFilter.GaussianBlur(0.34)), support)
    cyan_glow = ImageChops.multiply(cyan.filter(ImageFilter.GaussianBlur(1.6)), support)

    result = frame.convert("RGBA")
    alpha = result.getchannel("A")
    reduction = holes.point(lambda value: round(value * 0.30))
    result.putalpha(ImageChops.subtract(alpha, reduction))

    inner = _hex_rgb(str(params["colors.inner"]))
    result = Image.alpha_composite(result, _mask_layer(cyan_glow, inner, 0.12))
    result = Image.alpha_composite(result, _mask_layer(cyan_sharp, inner, 0.34))
    return result


def apply_body_texture_to_frames(
    frame_paths: list[Path],
    params: dict[str, str | float | int],
    *,
    seed: int,
) -> None:
    frame_count = len(frame_paths)
    for frame_index, frame_path in enumerate(frame_paths):
        frame = Image.open(frame_path).convert("RGBA")
        add_body_texture(
            frame,
            params,
            seed=seed,
            frame_index=frame_index,
            frame_count=frame_count,
        ).save(frame_path)
