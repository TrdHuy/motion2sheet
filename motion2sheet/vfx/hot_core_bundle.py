from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .energy_graph import EnergyGraph, build_energy_graph, normalize, smoothstep01


def _hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def _mask_layer(mask: Image.Image, color: tuple[int, int, int], amount: float) -> Image.Image:
    alpha = mask.point(lambda value: max(0, min(255, round(value * amount))))
    layer = Image.new("RGBA", mask.size, (*color, 0))
    layer.putalpha(alpha)
    return layer


def _draw_strip(mask: Image.Image, points: list[tuple[float, float]], widths: list[float], values: list[int], scale: int) -> None:
    if len(points) < 2:
        return
    draw = ImageDraw.Draw(mask)
    for index in range(len(points) - 1):
        p0 = (points[index][0] * scale, points[index][1] * scale)
        p1 = (points[index + 1][0] * scale, points[index + 1][1] * scale)
        width = max(1, round((widths[index] + widths[index + 1]) * 0.5 * scale))
        value = max(values[index], values[index + 1])
        draw.line([p0, p1], fill=value, width=width)


def _stroke_alive(seed: int, stroke_index: int, breakup: float) -> tuple[bool, float]:
    rng = random.Random(seed * 104729 + stroke_index * 7919 + 193)
    # White-hot energy disappears early in the approved decay. Keep only cyan/
    # blue residual fragments for the final frames.
    death = rng.uniform(0.58, 0.80)
    if breakup <= death:
        return True, 1.0
    excess = (breakup - death) / max(0.04, 1.0 - death)
    return excess < 0.72, max(0.0, 1.0 - excess * 1.20)


def _core_stroke(
    graph: EnergyGraph,
    *,
    seed: int,
    stroke_index: int,
    width_scale: float,
    offset: float,
) -> tuple[list[tuple[float, float]], list[float], list[int]]:
    rng = random.Random(seed * 65537 + stroke_index * 12289 + 883)
    phase_a = rng.uniform(0.0, math.tau)
    phase_b = rng.uniform(0.0, math.tau)
    frequency = rng.uniform(1.65, 3.80)
    offset_wave = rng.uniform(0.035, 0.14)
    width_wave = rng.uniform(0.24, 0.48)
    points: list[tuple[float, float]] = []
    widths: list[float] = []
    values: list[int] = []
    count = len(graph.nodes)
    for index, node in enumerate(graph.nodes):
        u = index / max(1, count - 1)
        local_offset = offset + math.sin(u * math.tau * frequency + phase_a) * offset_wave
        local_offset += math.sin(u * math.tau * frequency * 0.43 + phase_b) * offset_wave * 0.38
        points.append((
            node.point[0] + node.normal[0] * node.width * local_offset,
            node.point[1] + node.normal[1] * node.width * local_offset,
        ))
        taper = smoothstep01(u / 0.055) * smoothstep01((1.0 - u) / 0.05)
        taper = max(0.20, taper)
        modulation = 1.0 + math.sin(u * math.tau * frequency + phase_b) * width_wave
        modulation += math.sin(u * math.tau * frequency * 1.73 - phase_a) * width_wave * 0.24
        # Controlled pinches create cyan gaps between neighboring white strokes
        # without disconnecting the whole cutting trajectory.
        for pinch_center in (0.28 + stroke_index * 0.045, 0.66 - stroke_index * 0.025):
            distance = abs(u - pinch_center)
            if distance < 0.055:
                modulation *= 0.34 + 0.66 * (distance / 0.055)
        widths.append(max(0.45, node.width * width_scale * max(0.20, modulation) * taper))
        hotspot = 0.82 + 0.18 * max(0.0, math.sin(u * math.tau * (frequency * 0.55) + phase_a))
        values.append(round(255 * hotspot))
    return points, widths, values


def _cyan_support_stroke(
    graph: EnergyGraph,
    *,
    seed: int,
    index: int,
) -> tuple[list[tuple[float, float]], list[float], list[int]]:
    rng = random.Random(seed * 262147 + index * 3571 + 401)
    phase = rng.uniform(0.0, math.tau)
    offset = rng.uniform(-0.48, 0.18)
    width_scale = rng.uniform(0.28, 0.52)
    points: list[tuple[float, float]] = []
    widths: list[float] = []
    values: list[int] = []
    for node_index, node in enumerate(graph.nodes):
        u = node_index / max(1, len(graph.nodes) - 1)
        local = offset + math.sin(u * math.tau * rng.uniform(1.1, 2.5) + phase) * rng.uniform(0.05, 0.18)
        points.append((node.point[0] + node.normal[0] * node.width * local, node.point[1] + node.normal[1] * node.width * local))
        envelope = smoothstep01(u / 0.08) * smoothstep01((1.0 - u) / 0.075)
        widths.append(max(0.5, node.width * width_scale * envelope * (0.78 + 0.22 * math.sin(u * math.tau * 2.3 + phase))))
        values.append(rng.randint(155, 220))
    return points, widths, values


def _fragment_sparks(graph: EnergyGraph, size: tuple[int, int], seed: int, frame_index: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    if graph.energy < 0.72 or graph.breakup > 0.76:
        return mask
    rng = random.Random(seed * 99991 + frame_index * 1597 + 31)
    draw = ImageDraw.Draw(mask)
    count = round(8 + 10 * graph.energy)
    for _ in range(count):
        node = graph.nodes[rng.randint(3, len(graph.nodes) - 4)]
        radial = rng.uniform(0.9, 3.8) * node.width
        tangential = rng.uniform(-1.5, 1.5) * node.width
        x = node.point[0] + node.normal[0] * radial + node.tangent[0] * tangential
        y = node.point[1] + node.normal[1] * radial + node.tangent[1] * tangential
        radius = rng.uniform(0.45, 1.55)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=rng.randint(90, 190))
    return mask


def add_hot_core_bundle(
    frame: Image.Image,
    params: dict[str, str | float | int],
    *,
    seed: int,
    frame_index: int,
    frame_count: int,
) -> Image.Image:
    graph = build_energy_graph(frame.size, params, seed=seed, frame_index=frame_index, frame_count=frame_count)
    scale = 3
    large = (frame.width * scale, frame.height * scale)
    cyan_mask = Image.new("L", large, 0)
    white_mask = Image.new("L", large, 0)

    # Cyan is deliberately broader than white so the hot core reads as plasma
    # embedded in the blue body rather than a clean vector line.
    support_count = 4
    for support_index in range(support_count):
        points, widths, values = _cyan_support_stroke(graph, seed=seed + frame_index * 97, index=support_index)
        _draw_strip(cyan_mask, points, widths, values, scale)

    core_count = max(3, min(5, int(params["core.streak_count"])))
    offsets = (-0.38, -0.27, -0.17, -0.08, 0.02)
    width_scales = (0.30, 0.39, 0.28, 0.34, 0.23)
    for stroke_index in range(core_count):
        alive, opacity = _stroke_alive(seed + frame_index * 131, stroke_index, graph.breakup)
        if not alive or opacity <= 0.02:
            continue
        points, widths, values = _core_stroke(
            graph,
            seed=seed + frame_index * 131,
            stroke_index=stroke_index,
            width_scale=width_scales[stroke_index],
            offset=offsets[stroke_index],
        )
        values = [round(value * opacity) for value in values]
        _draw_strip(white_mask, points, widths, values, scale)

    cyan_mask = cyan_mask.resize(frame.size, Image.Resampling.LANCZOS)
    white_mask = white_mask.resize(frame.size, Image.Resampling.LANCZOS)
    sparks = _fragment_sparks(graph, frame.size, seed, frame_index)

    body = _hex_rgb(str(params["colors.body"]))
    inner = _hex_rgb(str(params["colors.inner"]))
    core = _hex_rgb(str(params["colors.core"]))
    result = frame.convert("RGBA")

    # Soft blue/cyan bloom first, then the irregular hot strokes. Alpha values
    # are intentionally additive-looking but remain deterministic RGBA layers.
    cyan_wide = cyan_mask.filter(ImageFilter.GaussianBlur(7.0))
    cyan_tight = cyan_mask.filter(ImageFilter.GaussianBlur(2.5))
    white_glow = white_mask.filter(ImageFilter.GaussianBlur(3.5))
    result = Image.alpha_composite(result, _mask_layer(cyan_wide, body, 0.16))
    result = Image.alpha_composite(result, _mask_layer(cyan_tight, inner, 0.32))
    result = Image.alpha_composite(result, _mask_layer(white_glow, inner, 0.30))
    result = Image.alpha_composite(result, _mask_layer(cyan_mask.filter(ImageFilter.GaussianBlur(0.45)), inner, 0.46))
    result = Image.alpha_composite(result, _mask_layer(white_mask.filter(ImageFilter.GaussianBlur(0.55)), core, 0.82))
    result = Image.alpha_composite(result, _mask_layer(sparks.filter(ImageFilter.GaussianBlur(1.8)), inner, 0.35))
    result = Image.alpha_composite(result, _mask_layer(sparks, core, 0.42))
    return result


def apply_hot_core_bundle_to_frames(
    frame_paths: list[Path],
    params: dict[str, str | float | int],
    *,
    seed: int,
) -> None:
    frame_count = len(frame_paths)
    for frame_index, frame_path in enumerate(frame_paths):
        frame = Image.open(frame_path).convert("RGBA")
        add_hot_core_bundle(
            frame,
            params,
            seed=seed,
            frame_index=frame_index,
            frame_count=frame_count,
        ).save(frame_path)
