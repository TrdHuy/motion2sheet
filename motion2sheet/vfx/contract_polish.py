from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .energy_graph import EnergyGraph, EnergyNode, build_energy_graph, normalize


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
        local = local * 0.72 + rng.uniform(1.0 - width_jitter, 1.0 + width_jitter) * 0.28
        width = max(1, round((left.width + right.width) * 0.5 * width_scale * local))
        energy = max(0.0, min(1.0, (left.energy + right.energy) * 0.5))
        draw.line([left.point, right.point], fill=round(value * (0.82 + 0.18 * energy)), width=width)
    return mask


def _core_hierarchy_masks(
    size: tuple[int, int],
    graph: EnergyGraph,
    params: dict[str, str | float | int],
    rng: random.Random,
) -> tuple[Image.Image, Image.Image]:
    # The approved reference has a broad cyan plasma transition but only a
    # narrow irregular white-hot center. Keep both on the exact shared graph.
    cyan = _draw_graph_strip(
        size,
        graph,
        width_scale=2.15,
        value=238,
        rng=rng,
        width_jitter=0.22,
    ).filter(ImageFilter.GaussianBlur(2.2))
    hot = _draw_graph_strip(
        size,
        graph,
        width_scale=0.46,
        value=255,
        rng=rng,
        width_jitter=max(0.20, float(params["core.width_jitter"]) * 0.72),
    ).filter(ImageFilter.GaussianBlur(0.65))
    return cyan, hot


def _density_holes(
    size: tuple[int, int],
    graph: EnergyGraph,
    params: dict[str, str | float | int],
    rng: random.Random,
) -> Image.Image:
    """Create elongated negative-energy pockets following local slash flow."""
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    if len(graph.nodes) < 10:
        return mask
    detail = float(params["shape.detail_noise"])
    count = 5 + round(detail * 6)
    body_scale = float(params["shape.body_scale"])
    candidates = list(range(5, len(graph.nodes) - 5))
    rng.shuffle(candidates)
    for node_index in candidates[:count]:
        node = graph.nodes[node_index]
        tx, ty = node.tangent
        nx, ny = node.normal
        tangent_length = node.width * body_scale * rng.uniform(1.4, 3.4)
        normal_shift = node.width * rng.uniform(-1.1, 1.1)
        cx = node.point[0] + nx * normal_shift
        cy = node.point[1] + ny * normal_shift
        start = (cx - tx * tangent_length * 0.5, cy - ty * tangent_length * 0.5)
        end = (cx + tx * tangent_length * 0.5, cy + ty * tangent_length * 0.5)
        width = max(2, round(node.width * rng.uniform(0.38, 0.90)))
        draw.line([start, end], fill=rng.randint(90, 170), width=width)
    return mask.filter(ImageFilter.GaussianBlur(3.2))


def _breakup_mask(
    size: tuple[int, int],
    graph: EnergyGraph,
    params: dict[str, str | float | int],
    rng: random.Random,
) -> Image.Image:
    """Cut graph-crossing gaps so decay changes topology instead of only alpha."""
    mask = Image.new("L", size, 0)
    if graph.breakup < 0.17 or len(graph.nodes) < 12:
        return mask
    draw = ImageDraw.Draw(mask)
    body_scale = float(params["shape.body_scale"])
    count = 1 + round(graph.breakup * 7)
    low = max(5, round(len(graph.nodes) * 0.10))
    high = min(len(graph.nodes) - 6, round(len(graph.nodes) * 0.88))
    slots = list(range(low, high))
    rng.shuffle(slots)
    for node_index in sorted(slots[:count]):
        node = graph.nodes[node_index]
        nx, ny = node.normal
        tx, ty = node.tangent
        extent = max(12.0, node.width * body_scale * rng.uniform(1.25, 2.20))
        tangent_shift = node.width * rng.uniform(-0.65, 0.65)
        cx = node.point[0] + tx * tangent_shift
        cy = node.point[1] + ty * tangent_shift
        start = (cx - nx * extent, cy - ny * extent)
        end = (cx + nx * extent, cy + ny * extent)
        width = max(3, round(node.width * (0.40 + 1.05 * graph.breakup) * rng.uniform(0.75, 1.25)))
        draw.line([start, end], fill=round(150 + 95 * graph.breakup), width=width)
    return mask.filter(ImageFilter.GaussianBlur(1.15 + graph.breakup * 1.4))


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
        breakup_amount = breakup_values[index] / 255.0
        white_energy = _is_white_energy(r, g, b, a)
        blue_energy = _is_blue_energy(r, g, b, a)

        # External lightning lives outside the graph corridor and should stay
        # readable; white inside the corridor is redistributed into cyan except
        # for the much narrower white-hot spine.
        external_bolt = white_energy and cyan_amount < 0.16
        if cyan_amount > 0.06 and not external_bolt:
            cyan_target = _mix(body, inner, 0.84)
            target = _mix(cyan_target, core, hot_amount ** 1.75)
            blend = min(0.94, 0.42 + cyan_amount * 0.46 + hot_amount * 0.22)
            r, g, b = _mix((r, g, b), target, blend)
            if white_energy and hot_amount < 0.52:
                r, g, b = _mix((r, g, b), inner, 0.76)
        elif external_bolt:
            r, g, b = _mix((r, g, b), lightning, 0.34)

        # Painterly density: coherent modulation may remove as well as add
        # opacity/brightness. High-energy core and external bolts are protected.
        if blue_energy and hot_amount < 0.38 and not external_bolt:
            flow = (
                math.sin((x / width) * math.tau * 4.1 + phase) * 0.45
                + math.sin((y / height) * math.tau * 3.0 - phase * 0.72) * 0.30
                + math.sin(((x + y) / (width + height)) * math.tau * 7.4 + phase * 1.31) * 0.25
            )
            density = max(0.42, min(1.08, 0.88 + flow * 0.16 - hole_amount * 0.42))
            a = round(a * density)
            if density < 0.86:
                r, g, b = _mix((r, g, b), outer, min(0.44, (0.86 - density) * 1.8))

        # Decay must physically disconnect the crescent. Cross-graph gaps remove
        # ordinary body strongly while preserving a little residual electric detail.
        if breakup_amount > 0.02:
            protected = max(hot_amount, 0.72 if external_bolt else 0.0)
            removal = breakup_amount * (1.0 - protected * 0.68)
            a = round(a * max(0.05, 1.0 - removal * 0.94))
            if removal > 0.38 and blue_energy:
                r, g, b = _mix((r, g, b), outer, min(0.55, removal * 0.62))

        if graph.breakup > 0.62 and blue_energy and hot_amount < 0.32 and not external_bolt:
            # Final frames should not retain an intact mini-crescent.
            retention = max(0.18, 1.0 - (graph.breakup - 0.62) * 1.55)
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
        polish_frame(
            frame,
            params,
            seed=seed,
            frame_index=frame_index,
            frame_count=frame_count,
        ).save(frame_path)
