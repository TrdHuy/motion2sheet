from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .energy_graph import EnergyGraph, build_energy_graph


def _hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, amount))
    return tuple(round(left * (1.0 - t) + right * t) for left, right in zip(a, b))


def _draw_graph_strip(
    size: tuple[int, int],
    graph: EnergyGraph,
    *,
    width_scale: float,
    value: int,
    rng: random.Random,
    width_jitter: float,
) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    local = 1.0
    for index in range(len(graph.nodes) - 1):
        left = graph.nodes[index]
        right = graph.nodes[index + 1]
        local = local * 0.70 + rng.uniform(1.0 - width_jitter, 1.0 + width_jitter) * 0.30
        width = max(1, round((left.width + right.width) * 0.5 * width_scale * local))
        energy = max(0.0, min(1.0, (left.energy + right.energy) * 0.5))
        draw.line([left.point, right.point], fill=round(value * (0.80 + 0.20 * energy)), width=width)
    return mask


def _core_hierarchy_masks(
    size: tuple[int, int],
    graph: EnergyGraph,
    params: dict[str, str | float | int],
    rng: random.Random,
) -> tuple[Image.Image, Image.Image]:
    cyan = _draw_graph_strip(
        size, graph, width_scale=2.05, value=238, rng=rng, width_jitter=0.28
    ).filter(ImageFilter.GaussianBlur(2.0))
    hot = _draw_graph_strip(
        size,
        graph,
        width_scale=0.54,
        value=255,
        rng=rng,
        width_jitter=max(0.24, float(params["core.width_jitter"]) * 0.78),
    ).filter(ImageFilter.GaussianBlur(0.60))
    return cyan, hot


def _density_holes(
    size: tuple[int, int],
    graph: EnergyGraph,
    params: dict[str, str | float | int],
    rng: random.Random,
) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    if len(graph.nodes) < 10:
        return mask
    detail = float(params["shape.detail_noise"])
    count = 8 + round(detail * 9)
    body_scale = float(params["shape.body_scale"])
    candidates = list(range(4, len(graph.nodes) - 4))
    rng.shuffle(candidates)
    for node_index in candidates[:count]:
        node = graph.nodes[node_index]
        tx, ty = node.tangent
        nx, ny = node.normal
        tangent_length = node.width * body_scale * rng.uniform(1.6, 4.2)
        normal_shift = node.width * rng.uniform(-1.25, 1.25)
        cx = node.point[0] + nx * normal_shift
        cy = node.point[1] + ny * normal_shift
        curve = rng.uniform(-0.22, 0.22) * tangent_length
        start = (cx - tx * tangent_length * 0.5 - nx * curve * 0.25, cy - ty * tangent_length * 0.5 - ny * curve * 0.25)
        mid = (cx + nx * curve, cy + ny * curve)
        end = (cx + tx * tangent_length * 0.5 - nx * curve * 0.20, cy + ty * tangent_length * 0.5 - ny * curve * 0.20)
        width = max(2, round(node.width * rng.uniform(0.42, 1.05)))
        draw.line([start, mid, end], fill=rng.randint(120, 205), width=width)
    return mask.filter(ImageFilter.GaussianBlur(2.7))


def _flow_highlights(
    size: tuple[int, int],
    graph: EnergyGraph,
    params: dict[str, str | float | int],
    rng: random.Random,
) -> Image.Image:
    """Embedded cyan streaks make the blue mass read as flowing plasma, not a flat slab."""
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    if len(graph.nodes) < 12:
        return mask
    detail = float(params["shape.detail_noise"])
    body_scale = float(params["shape.body_scale"])
    count = 9 + round(detail * 7)
    indices = list(range(5, len(graph.nodes) - 5))
    rng.shuffle(indices)
    for node_index in indices[:count]:
        node = graph.nodes[node_index]
        tx, ty = node.tangent
        nx, ny = node.normal
        normal_shift = node.width * rng.uniform(-1.45, 1.45)
        cx = node.point[0] + nx * normal_shift
        cy = node.point[1] + ny * normal_shift
        length = node.width * body_scale * rng.uniform(1.0, 3.1)
        bend = node.width * rng.uniform(-0.90, 0.90)
        start = (cx - tx * length * 0.50, cy - ty * length * 0.50)
        mid = (cx + nx * bend, cy + ny * bend)
        end = (cx + tx * length * 0.50, cy + ty * length * 0.50)
        width = max(1, round(node.width * rng.uniform(0.18, 0.48)))
        draw.line([start, mid, end], fill=rng.randint(95, 185), width=width)
    return mask.filter(ImageFilter.GaussianBlur(1.2))


def _breakup_mask(
    size: tuple[int, int],
    graph: EnergyGraph,
    params: dict[str, str | float | int],
    rng: random.Random,
) -> Image.Image:
    mask = Image.new("L", size, 0)
    if graph.breakup < 0.17 or len(graph.nodes) < 12:
        return mask
    draw = ImageDraw.Draw(mask)
    body_scale = float(params["shape.body_scale"])
    count = 1 + round(graph.breakup * 8)
    low = max(5, round(len(graph.nodes) * 0.10))
    high = min(len(graph.nodes) - 6, round(len(graph.nodes) * 0.88))
    slots = list(range(low, high))
    rng.shuffle(slots)
    for node_index in sorted(slots[:count]):
        node = graph.nodes[node_index]
        nx, ny = node.normal
        tx, ty = node.tangent
        extent = max(12.0, node.width * body_scale * rng.uniform(1.45, 2.55))
        tangent_shift = node.width * rng.uniform(-0.65, 0.65)
        cx = node.point[0] + tx * tangent_shift
        cy = node.point[1] + ty * tangent_shift
        start = (cx - nx * extent, cy - ny * extent)
        end = (cx + nx * extent, cy + ny * extent)
        width = max(3, round(node.width * (0.44 + 1.18 * graph.breakup) * rng.uniform(0.80, 1.32)))
        draw.line([start, end], fill=round(160 + 90 * graph.breakup), width=width)
    return mask.filter(ImageFilter.GaussianBlur(1.0 + graph.breakup * 1.25))


def _is_white_energy(r: int, g: int, b: int, a: int) -> bool:
    return a > 16 and r > 176 and g > 188 and b > 198


def _is_blue_energy(r: int, g: int, b: int, a: int) -> bool:
    return a > 10 and b > 105 and b >= r * 1.10


def polish_frame(
    frame: Image.Image,
    params: dict[str, str | float | int],
    *,
    seed: int,
    frame_index: int,
    frame_count: int,
) -> Image.Image:
    rgba = frame.convert("RGBA")
    graph = build_energy_graph(rgba.size, params, seed=seed, frame_index=frame_index, frame_count=frame_count)
    rng = random.Random(seed * 1900813 + frame_index * 12289 + 1601)
    cyan_mask, hot_mask = _core_hierarchy_masks(rgba.size, graph, params, rng)
    holes = _density_holes(rgba.size, graph, params, rng)
    highlights = _flow_highlights(rgba.size, graph, params, rng)
    breakup = _breakup_mask(rgba.size, graph, params, rng)

    inner = _hex_rgb(str(params["colors.inner"]))
    body = _hex_rgb(str(params["colors.body"]))
    outer = _hex_rgb(str(params["colors.outer"]))
    core = _hex_rgb(str(params["colors.core"]))
    lightning = _hex_rgb(str(params["colors.lightning"]))
    pixels = list(rgba.getdata())
    cyan_values = list(cyan_mask.getdata())
    hot_values = list(hot_mask.getdata())
    hole_values = list(holes.getdata())
    highlight_values = list(highlights.getdata())
    breakup_values = list(breakup.getdata())
    width, height = rgba.size
    phase = (seed * 0.00217 + frame_index * 0.733) % math.tau
    output: list[tuple[int, int, int, int]] = []

    for index, (r, g, b, a) in enumerate(pixels):
        if a <= 1:
            output.append((0, 0, 0, 0))
            continue
        x = index % width
        y = index // width
        cyan_amount = cyan_values[index] / 255.0
        hot_amount = hot_values[index] / 255.0
        hole_amount = hole_values[index] / 255.0
        highlight_amount = highlight_values[index] / 255.0
        breakup_amount = breakup_values[index] / 255.0
        white_energy = _is_white_energy(r, g, b, a)
        blue_energy = _is_blue_energy(r, g, b, a)

        external_bolt = white_energy and cyan_amount < 0.16
        if cyan_amount > 0.06 and not external_bolt:
            cyan_target = _mix(body, inner, 0.88)
            target = _mix(cyan_target, core, hot_amount ** 1.62)
            blend = min(0.95, 0.44 + cyan_amount * 0.44 + hot_amount * 0.24)
            r, g, b = _mix((r, g, b), target, blend)
            if white_energy and hot_amount < 0.50:
                r, g, b = _mix((r, g, b), inner, 0.80)
        elif external_bolt:
            r, g, b = _mix((r, g, b), lightning, 0.34)

        if blue_energy and hot_amount < 0.40 and not external_bolt:
            flow = (
                math.sin((x / width) * math.tau * 4.3 + phase) * 0.44
                + math.sin((y / height) * math.tau * 3.2 - phase * 0.72) * 0.31
                + math.sin(((x + y) / (width + height)) * math.tau * 7.9 + phase * 1.31) * 0.25
            )
            density = max(0.18, min(1.08, 0.78 + flow * 0.22 - hole_amount * 0.62))
            a = round(a * density)
            if density < 0.82:
                r, g, b = _mix((r, g, b), outer, min(0.55, (0.82 - density) * 1.75))
            if highlight_amount > 0.05:
                highlight_color = _mix(body, inner, 0.82)
                r, g, b = _mix((r, g, b), highlight_color, min(0.60, highlight_amount * 0.72))
                a = max(a, round(min(255, a + highlight_amount * 42)))

        if breakup_amount > 0.02:
            protected = max(hot_amount, 0.72 if external_bolt else 0.0)
            removal = breakup_amount * (1.0 - protected * 0.68)
            a = round(a * max(0.03, 1.0 - removal * 0.98))
            if removal > 0.32 and blue_energy:
                r, g, b = _mix((r, g, b), outer, min(0.62, removal * 0.70))

        if graph.breakup > 0.58 and blue_energy and hot_amount < 0.34 and not external_bolt:
            retention = max(0.10, 1.0 - (graph.breakup - 0.58) * 1.72)
            a = round(a * retention)

        output.append((max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)), max(0, min(255, a))))

    result = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    result.putdata(output)
    return result


def apply_contract_polish_to_frames(
    frame_paths: list[Path],
    params: dict[str, str | float | int],
    *,
    seed: int,
) -> None:
    frame_count = len(frame_paths)
    for frame_index, frame_path in enumerate(frame_paths):
        frame = Image.open(frame_path).convert("RGBA")
        polish_frame(frame, params, seed=seed, frame_index=frame_index, frame_count=frame_count).save(frame_path)
