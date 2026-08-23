from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .energy_graph import EnergyGraph, EnergyNode, build_energy_graph, normalize


def _hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def _path(
    node: EnergyNode,
    *,
    side: float,
    length: float,
    segments: int,
    jitter: float,
    rng: random.Random,
) -> list[tuple[float, float]]:
    tx, ty = node.tangent
    nx, ny = node.normal[0] * side, node.normal[1] * side
    root_inside = (
        node.point[0] - nx * node.width * 0.32 - tx * node.width * 0.10,
        node.point[1] - ny * node.width * 0.32 - ty * node.width * 0.10,
    )
    root_mid = node.point
    root_edge = (
        node.point[0] + nx * node.width * 0.52,
        node.point[1] + ny * node.width * 0.52,
    )
    points = [root_inside, root_mid, root_edge]
    tangent_bias = rng.uniform(-0.72, 0.72)
    dx, dy = normalize(nx + tx * tangent_bias, ny + ty * tangent_bias)
    angle = math.atan2(dy, dx)
    x, y = root_edge
    remaining = max(1.0, length - node.width * 0.52)
    step = remaining / max(1, segments)
    for segment in range(segments):
        progress = (segment + 1) / segments
        angle += rng.uniform(-0.40, 0.40) * jitter * (0.74 + 0.32 * progress)
        local = step * rng.uniform(0.78, 1.22)
        dx, dy = math.cos(angle), math.sin(angle)
        px, py = -dy, dx
        lateral = step * jitter * rng.uniform(-0.30, 0.30)
        x += dx * local + px * lateral
        y += dy * local + py * lateral
        points.append((x, y))
    return points


def _widths(
    count: int,
    base: float,
    tip: float,
    params: dict[str, str | float | int],
    rng: random.Random,
) -> list[float]:
    jitter = float(params["lightning.width_jitter"])
    smoothness = float(params["lightning.width_smoothness"])
    taper_power = float(params["lightning.taper_power"])
    noise = [1.0 + rng.uniform(-jitter, jitter) for _ in range(count)]
    for _ in range(2):
        previous = noise[:]
        for index in range(1, count - 1):
            average = previous[index - 1] * 0.25 + previous[index] * 0.50 + previous[index + 1] * 0.25
            noise[index] = previous[index] * (1.0 - smoothness) + average * smoothness
    result: list[float] = []
    for index, local in enumerate(noise):
        t = index / max(1, count - 1)
        nominal = tip + max(0.0, base - tip) * ((1.0 - t) ** taper_power)
        result.append(max(tip * 0.72, nominal * local))
    result[-1] = tip * rng.uniform(0.72, 1.0)
    return result


def _draw_strip(
    mask: Image.Image,
    points: list[tuple[float, float]],
    widths: list[float],
    value: int,
) -> None:
    draw = ImageDraw.Draw(mask)
    for index in range(len(points) - 1):
        width = max(1, round((widths[index] + widths[index + 1]) * 0.5))
        draw.line([points[index], points[index + 1]], fill=value, width=width)


def _fork_direction(points: list[tuple[float, float]], index: int, rng: random.Random) -> tuple[float, float]:
    previous = points[max(0, index - 1)]
    following = points[min(len(points) - 1, index + 1)]
    tx, ty = normalize(following[0] - previous[0], following[1] - previous[1])
    angle = math.atan2(ty, tx) + rng.uniform(0.52, 0.96) * (1.0 if rng.random() > 0.5 else -1.0)
    return math.cos(angle), math.sin(angle)


def _free_path(
    origin: tuple[float, float],
    direction: tuple[float, float],
    length: float,
    segments: int,
    jitter: float,
    rng: random.Random,
) -> list[tuple[float, float]]:
    dx, dy = normalize(*direction)
    angle = math.atan2(dy, dx)
    x, y = origin
    points = [(x, y)]
    step = length / max(1, segments)
    for _ in range(segments):
        angle += rng.uniform(-0.40, 0.40) * jitter
        local = step * rng.uniform(0.76, 1.22)
        x += math.cos(angle) * local
        y += math.sin(angle) * local
        points.append((x, y))
    return points


def _draw_tree(
    mask: Image.Image,
    points: list[tuple[float, float]],
    widths: list[float],
    params: dict[str, str | float | int],
    rng: random.Random,
    *,
    depth: int,
) -> None:
    _draw_strip(mask, points, widths, 255 if depth == 0 else 218)
    if depth >= min(2, int(params["lightning.branch_depth"])):
        return
    probability = float(params["lightning.branch_probability"]) * (0.74 ** depth)
    candidates = list(range(3, max(4, len(points) - 2)))
    rng.shuffle(candidates)
    spawned = 0
    for index in candidates:
        if spawned >= (2 if depth == 0 else 1) or rng.random() > probability:
            continue
        spawned += 1
        child_length = math.dist(points[0], points[-1]) * float(params["lightning.minor_length_ratio"]) * rng.uniform(0.62, 0.88)
        child_points = _free_path(
            points[index],
            _fork_direction(points, index, rng),
            child_length,
            5,
            float(params["lightning.jitter"]) * 1.12,
            rng,
        )
        child_base = widths[index] * float(params["lightning.minor_width_ratio"]) * rng.uniform(0.82, 1.06)
        child_widths = _widths(
            len(child_points),
            max(0.55, child_base),
            max(0.12, float(params["lightning.tip_width"]) * 0.76),
            params,
            rng,
        )
        _draw_tree(mask, child_points, child_widths, params, rng, depth=depth + 1)


def _build_mask(
    graph: EnergyGraph,
    size: tuple[int, int],
    params: dict[str, str | float | int],
    rng: random.Random,
) -> Image.Image:
    mask = Image.new("L", size, 0)
    if graph.energy < 0.58 or len(graph.nodes) < 16:
        return mask
    min_dim = min(size)
    anchors = [round(len(graph.nodes) * 0.30), round(len(graph.nodes) * 0.66)]
    for anchor in anchors:
        node = graph.nodes[max(3, min(len(graph.nodes) - 4, anchor))]
        length = min_dim * float(params["lightning.length"]) * rng.uniform(0.13, 0.19) * (0.80 + 0.20 * graph.energy)
        points = _path(
            node,
            side=-1.0,
            length=length,
            segments=7,
            jitter=float(params["lightning.jitter"]),
            rng=rng,
        )
        base = rng.uniform(float(params["lightning.major_width_min"]), float(params["lightning.major_width_max"])) * 0.86
        root_base = max(base, node.width * float(params["energy.root_width_coupling"]) * 0.82)
        widths = _widths(len(points), root_base, float(params["lightning.tip_width"]), params, rng)
        widths[0] = max(widths[0], node.width * 0.56)
        widths[1] = max(widths[1], node.width * 0.62)
        _draw_tree(mask, points, widths, params, rng, depth=0)
    return mask.filter(ImageFilter.GaussianBlur(0.32))


def add_bilateral_lightning(
    frame: Image.Image,
    params: dict[str, str | float | int],
    *,
    seed: int,
    frame_index: int,
    frame_count: int,
) -> Image.Image:
    graph = build_energy_graph(frame.size, params, seed=seed, frame_index=frame_index, frame_count=frame_count)
    rng = random.Random(seed * 524287 + frame_index * 8191 + 1877)
    mask = _build_mask(graph, frame.size, params, rng)
    if mask.getbbox() is None:
        return frame
    lightning_rgb = _hex_rgb(str(params["colors.lightning"]))
    core_rgb = _hex_rgb(str(params["colors.core"]))
    glow = mask.filter(ImageFilter.GaussianBlur(max(1.5, float(params["lightning.glow_radius"]) * 0.62)))
    glow = glow.point(lambda value: round(value * min(0.62, float(params["lightning.glow_strength"]) * 0.58)))
    glow_layer = Image.new("RGBA", frame.size, (*lightning_rgb, 0))
    glow_layer.putalpha(glow)
    cyan_layer = Image.new("RGBA", frame.size, (*lightning_rgb, 0))
    cyan_layer.putalpha(mask.point(lambda value: round(value * 0.82)))
    core_mask = mask.filter(ImageFilter.MinFilter(3)).point(lambda value: round(value * 0.64))
    core_layer = Image.new("RGBA", frame.size, (*core_rgb, 0))
    core_layer.putalpha(core_mask)
    result = Image.alpha_composite(frame.convert("RGBA"), glow_layer)
    result = Image.alpha_composite(result, cyan_layer)
    return Image.alpha_composite(result, core_layer)


def apply_bilateral_lightning_to_frames(
    frame_paths: list[Path],
    params: dict[str, str | float | int],
    *,
    seed: int,
) -> None:
    frame_count = len(frame_paths)
    for frame_index, frame_path in enumerate(frame_paths):
        frame = Image.open(frame_path).convert("RGBA")
        add_bilateral_lightning(
            frame,
            params,
            seed=seed,
            frame_index=frame_index,
            frame_count=frame_count,
        ).save(frame_path)
