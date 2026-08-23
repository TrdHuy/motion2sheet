from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .energy_graph import EnergyGraph, EnergyNode, build_energy_graph, normalize, smoothstep01


@dataclass(frozen=True)
class StrokeTier:
    name: str
    count: int
    offset_min: float
    offset_max: float
    width_min: float
    width_max: float
    alpha: int
    start_max: float
    end_min: float
    terminal_every: int
    death_min: float
    death_max: float


def _hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def _scale_mask(mask: Image.Image, size: tuple[int, int]) -> Image.Image:
    return mask.resize(size, Image.Resampling.LANCZOS)


def _mask_layer(mask: Image.Image, color: tuple[int, int, int], alpha_scale: float) -> Image.Image:
    alpha = mask.point(lambda value: max(0, min(255, round(value * alpha_scale))))
    result = Image.new("RGBA", mask.size, (*color, 0))
    result.putalpha(alpha)
    return result


def _stroke_window(seed: int, tier: StrokeTier, index: int, breakup: float) -> tuple[float, float, float] | None:
    rng = random.Random(seed * 1000003 + index * 7919 + sum(ord(ch) for ch in tier.name) * 97)
    death = rng.uniform(tier.death_min, tier.death_max)
    if breakup <= death:
        return 0.0, 1.0, 1.0
    denominator = max(0.05, 1.0 - min(0.98, death))
    excess = (breakup - death) / denominator
    if excess >= 0.82:
        return None
    center = rng.uniform(0.20, 0.80)
    span = max(0.12, 0.54 * (1.0 - excess))
    left = max(0.0, center - span * 0.5)
    right = min(1.0, center + span * 0.5)
    return left, right, max(0.22, 1.0 - excess * 0.72)


def _tier_blueprints(params: dict[str, str | float | int]) -> tuple[StrokeTier, ...]:
    # The reference is not a symmetric ribbon. Its white cutting edge sits on
    # the inner/open side while most blue plasma mass lives outward from it.
    # Keep the bundle sparse enough that transparent gaps survive between flows.
    body_count = max(24, min(32, int(params["shape.tongue_count"])))
    return (
        StrokeTier("outer", round(body_count * 0.68), 0.45, 2.05, 0.08, 0.18, 154, 0.26, 0.70, 3, 0.28, 1.04),
        StrokeTier("body", body_count, 0.05, 1.35, 0.11, 0.24, 198, 0.20, 0.75, 4, 0.34, 1.08),
        StrokeTier("cyan", max(9, round(body_count * 0.34)), -0.34, 0.38, 0.07, 0.16, 214, 0.14, 0.80, 6, 0.46, 1.12),
        StrokeTier("core", max(4, min(5, int(params["core.streak_count"]))), -0.46, -0.10, 0.055, 0.12, 238, 0.05, 0.88, 2, 0.58, 1.18),
    )


def _stroke_geometry(
    graph: EnergyGraph,
    tier: StrokeTier,
    index: int,
    params: dict[str, str | float | int],
    *,
    seed: int,
    min_dim: int,
) -> tuple[list[tuple[float, float]], list[float]]:
    rng = random.Random(seed * 65537 + index * 104729 + sum(ord(ch) for ch in tier.name) * 257)
    nodes = graph.nodes
    last = len(nodes) - 1
    start_fraction = rng.uniform(0.0, tier.start_max)
    end_fraction = rng.uniform(tier.end_min, 1.0)
    start = max(0, min(last - 4, round(start_fraction * last)))
    end = max(start + 4, min(last, round(end_fraction * last)))

    if tier.name == "core":
        start = min(start, 3 + index)
        end = max(end, last - 4 - index)

    offset_factor = rng.uniform(tier.offset_min, tier.offset_max)
    if tier.name == "outer":
        wave_amplitude = rng.uniform(0.06, 0.24)
    elif tier.name == "body":
        wave_amplitude = rng.uniform(0.05, 0.20)
    elif tier.name == "cyan":
        wave_amplitude = rng.uniform(0.04, 0.16)
    else:
        wave_amplitude = rng.uniform(0.025, 0.11)
    wave_frequency = rng.uniform(0.75, 2.35)
    tangent_wave = rng.uniform(0.02, 0.10)
    phase_a = rng.uniform(0.0, math.tau)
    phase_b = rng.uniform(0.0, math.tau)
    width_factor = rng.uniform(tier.width_min, tier.width_max)
    width_frequency = rng.uniform(1.2, 3.4)
    width_phase = rng.uniform(0.0, math.tau)
    local_width_amplitude = rng.uniform(0.14, 0.32) if tier.name != "core" else rng.uniform(0.18, 0.42)

    points: list[tuple[float, float]] = []
    widths: list[float] = []
    for node_index in range(start, end + 1):
        node = nodes[node_index]
        local_u = (node_index - start) / max(1, end - start)
        normal_offset = node.width * (
            offset_factor
            + math.sin(local_u * math.tau * wave_frequency + phase_a) * wave_amplitude
            + math.sin(local_u * math.tau * wave_frequency * 0.47 + phase_b) * wave_amplitude * 0.38
        )
        tangent_offset = node.width * math.sin(local_u * math.tau * 1.7 + phase_b) * tangent_wave
        points.append((
            node.point[0] + node.normal[0] * normal_offset + node.tangent[0] * tangent_offset,
            node.point[1] + node.normal[1] * normal_offset + node.tangent[1] * tangent_offset,
        ))
        envelope = smoothstep01(local_u / 0.11) * smoothstep01((1.0 - local_u) / 0.10)
        if tier.name == "core":
            envelope = max(0.30, envelope)
        local_width = 1.0 + math.sin(local_u * math.tau * width_frequency + width_phase) * local_width_amplitude
        widths.append(max(0.28, node.width * width_factor * local_width * envelope))

    # Long terminal flows extend the same stream. They create pointed crescent
    # tips without filling the open side with a broad triangular slab.
    if tier.terminal_every > 0 and index % tier.terminal_every == 0 and len(points) >= 3:
        tongue = float(params["shape.tongue_length"])
        extension = min_dim * tongue * rng.uniform(0.055, 0.125)
        steps = rng.randint(4, 6)
        if index % (tier.terminal_every * 2) == 0:
            first = nodes[start]
            tx, ty = -first.tangent[0], -first.tangent[1]
            x, y = points[0]
            extra_points: list[tuple[float, float]] = []
            extra_widths: list[float] = []
            for step in range(steps, 0, -1):
                u = step / steps
                bend = math.sin(u * math.pi) * extension * rng.uniform(-0.075, 0.075)
                px, py = -ty, tx
                extra_points.append((x + tx * extension * u + px * bend, y + ty * extension * u + py * bend))
                extra_widths.append(max(0.18, widths[0] * (0.12 + 0.34 * (1.0 - u))))
            points = extra_points + points
            widths = extra_widths + widths
        else:
            last_node = nodes[end]
            tx, ty = last_node.tangent
            x, y = points[-1]
            terminal_width = widths[-1]
            for step in range(1, steps + 1):
                u = step / steps
                bend = math.sin(u * math.pi) * extension * rng.uniform(-0.075, 0.075)
                px, py = -ty, tx
                points.append((x + tx * extension * u + px * bend, y + ty * extension * u + py * bend))
                widths.append(max(0.18, terminal_width * ((1.0 - u) ** 1.55)))

    return points, widths


def _slice_stroke(
    points: list[tuple[float, float]],
    widths: list[float],
    window: tuple[float, float, float],
) -> tuple[list[tuple[float, float]], list[float], float]:
    left, right, alpha = window
    if left <= 0.0 and right >= 1.0:
        return points, widths, alpha
    count = len(points)
    start = max(0, min(count - 2, round(left * (count - 1))))
    end = max(start + 1, min(count - 1, round(right * (count - 1))))
    return points[start:end + 1], widths[start:end + 1], alpha


def _draw_stroke(
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


def _render_flow_masks(
    graph: EnergyGraph,
    size: tuple[int, int],
    params: dict[str, str | float | int],
    *,
    seed: int,
) -> dict[str, Image.Image]:
    scale = 3
    large_size = (size[0] * scale, size[1] * scale)
    masks = {tier.name: Image.new("L", large_size, 0) for tier in _tier_blueprints(params)}
    min_dim = min(size)
    for tier in _tier_blueprints(params):
        for index in range(tier.count):
            window = _stroke_window(seed, tier, index, graph.breakup)
            if window is None:
                continue
            points, widths = _stroke_geometry(graph, tier, index, params, seed=seed, min_dim=min_dim)
            points, widths, alpha = _slice_stroke(points, widths, window)
            _draw_stroke(masks[tier.name], points, widths, round(tier.alpha * alpha), scale=scale)
    return {name: _scale_mask(mask, size) for name, mask in masks.items()}


def _bolt_widths(count: int, base: float, tip: float, rng: random.Random) -> list[float]:
    raw = [rng.uniform(0.72, 1.32) for _ in range(count)]
    for _ in range(2):
        previous = raw[:]
        for index in range(1, count - 1):
            raw[index] = previous[index] * 0.50 + previous[index - 1] * 0.25 + previous[index + 1] * 0.25
    result: list[float] = []
    for index, local in enumerate(raw):
        u = index / max(1, count - 1)
        nominal = tip + (base - tip) * ((1.0 - u) ** 1.35)
        result.append(max(tip * 0.72, nominal * local))
    result[-1] = tip
    return result


def _major_bolt_path(
    node: EnergyNode,
    side: float,
    length: float,
    jitter: float,
    rng: random.Random,
) -> list[tuple[float, float]]:
    tx, ty = node.tangent
    nx, ny = node.normal[0] * side, node.normal[1] * side
    points = [
        (node.point[0] - nx * node.width * 0.24 - tx * node.width * 0.10, node.point[1] - ny * node.width * 0.24 - ty * node.width * 0.10),
        node.point,
        (node.point[0] + nx * node.width * 0.46, node.point[1] + ny * node.width * 0.46),
    ]
    direction = normalize(nx + tx * rng.uniform(-0.82, 0.82), ny + ty * rng.uniform(-0.82, 0.82))
    angle = math.atan2(direction[1], direction[0])
    x, y = points[-1]
    segments = 7
    step = max(1.0, length - node.width * 0.46) / segments
    for segment in range(segments):
        progress = (segment + 1) / segments
        angle += rng.uniform(-0.42, 0.42) * jitter * (0.72 + progress * 0.38)
        local = step * rng.uniform(0.76, 1.24)
        dx, dy = math.cos(angle), math.sin(angle)
        px, py = -dy, dx
        lateral = step * jitter * rng.uniform(-0.34, 0.34)
        x += dx * local + px * lateral
        y += dy * local + py * lateral
        points.append((x, y))
    return points


def _free_bolt(
    origin: tuple[float, float],
    direction: tuple[float, float],
    length: float,
    rng: random.Random,
) -> list[tuple[float, float]]:
    dx, dy = normalize(*direction)
    angle = math.atan2(dy, dx)
    x, y = origin
    points = [(x, y)]
    for _ in range(5):
        angle += rng.uniform(-0.34, 0.34)
        local = length / 5.0 * rng.uniform(0.78, 1.20)
        x += math.cos(angle) * local
        y += math.sin(angle) * local
        points.append((x, y))
    return points


def _render_lightning_masks(
    graph: EnergyGraph,
    size: tuple[int, int],
    params: dict[str, str | float | int],
    *,
    seed: int,
    frame_index: int,
) -> tuple[Image.Image, Image.Image]:
    scale = 3
    large_size = (size[0] * scale, size[1] * scale)
    major = Image.new("L", large_size, 0)
    micro = Image.new("L", large_size, 0)
    rng = random.Random(seed * 524287 + frame_index * 12289 + 1877)
    if graph.energy < 0.56 or graph.breakup > 0.92:
        return _scale_mask(major, size), _scale_mask(micro, size)

    requested = max(2, min(4, int(params["lightning.major_count"])))
    count = max(1, round(requested * (0.82 + 0.18 * graph.energy) * (1.0 - graph.breakup * 0.56)))
    anchors = graph.major_anchor_indices(count, rng)
    min_dim = min(size)
    for bolt_index, anchor in enumerate(anchors):
        life_rng = random.Random(seed * 900001 + bolt_index * 3571)
        if graph.breakup > life_rng.uniform(0.62, 1.08):
            continue
        node = graph.nodes[anchor]
        side = -1.0 if bolt_index % 2 == 0 else 1.0
        length = min_dim * float(params["lightning.length"]) * rng.uniform(0.12, 0.19)
        points = _major_bolt_path(node, side, length, float(params["lightning.jitter"]), rng)
        base = rng.uniform(float(params["lightning.major_width_min"]), float(params["lightning.major_width_max"])) * 0.62
        base = max(base, node.width * 0.20)
        widths = _bolt_widths(len(points), base, float(params["lightning.tip_width"]), rng)
        _draw_stroke(major, points, widths, 246, scale=scale)

        branch_probability = float(params["lightning.branch_probability"])
        branch_candidates = list(range(4, max(5, len(points) - 2)))
        rng.shuffle(branch_candidates)
        spawned = 0
        for candidate in branch_candidates:
            if spawned >= 2 or rng.random() > branch_probability:
                continue
            spawned += 1
            previous = points[candidate - 1]
            following = points[candidate + 1]
            tx, ty = normalize(following[0] - previous[0], following[1] - previous[1])
            angle = math.atan2(ty, tx) + rng.uniform(0.55, 0.96) * (1.0 if rng.random() > 0.5 else -1.0)
            child_length = length * float(params["lightning.minor_length_ratio"]) * rng.uniform(0.42, 0.70)
            child = _free_bolt(points[candidate], (math.cos(angle), math.sin(angle)), child_length, rng)
            child_base = max(0.55, widths[candidate] * float(params["lightning.minor_width_ratio"]))
            child_widths = _bolt_widths(len(child), child_base, max(0.14, float(params["lightning.tip_width"]) * 0.72), rng)
            _draw_stroke(major, child, child_widths, 216, scale=scale)

    micro_count = max(6, min(16, int(params["lightning.micro_count"])))
    micro_count = round(micro_count * (1.0 - graph.breakup * 0.62))
    for _ in range(micro_count):
        node = graph.nodes[rng.randint(4, len(graph.nodes) - 5)]
        side = -1.0 if rng.random() < 0.5 else 1.0
        direction = normalize(
            node.normal[0] * side + node.tangent[0] * rng.uniform(-1.2, 1.2),
            node.normal[1] * side + node.tangent[1] * rng.uniform(-1.2, 1.2),
        )
        length = min_dim * rng.uniform(0.018, 0.045) * float(params["lightning.length"])
        path = _free_bolt(node.point, direction, length, rng)
        widths = _bolt_widths(len(path), rng.uniform(0.50, 1.10), 0.14, rng)
        _draw_stroke(micro, path, widths, 128, scale=scale)
    return _scale_mask(major, size), _scale_mask(micro, size)


def _compose_bundle(
    size: tuple[int, int],
    masks: dict[str, Image.Image],
    major: Image.Image,
    micro: Image.Image,
    params: dict[str, str | float | int],
) -> Image.Image:
    outer = _hex_rgb(str(params["colors.outer"]))
    body = _hex_rgb(str(params["colors.body"]))
    inner = _hex_rgb(str(params["colors.inner"]))
    core = _hex_rgb(str(params["colors.core"]))
    lightning = _hex_rgb(str(params["colors.lightning"]))
    result = Image.new("RGBA", size, (0, 0, 0, 0))

    # Glow follows sparse strokes rather than manufacturing a continuous body.
    outer_glow = masks["outer"].filter(ImageFilter.GaussianBlur(8.0))
    body_glow = masks["body"].filter(ImageFilter.GaussianBlur(5.2))
    cyan_glow = masks["cyan"].filter(ImageFilter.GaussianBlur(3.2))
    core_glow = masks["core"].filter(ImageFilter.GaussianBlur(2.0))
    major_glow = major.filter(ImageFilter.GaussianBlur(max(2.2, float(params["lightning.glow_radius"]) * 0.62)))

    for mask, color, alpha_scale in (
        (outer_glow, outer, 0.18),
        (body_glow, body, 0.18),
        (cyan_glow, inner, 0.16),
        (core_glow, inner, 0.13),
        (major_glow, lightning, 0.22),
        (masks["outer"].filter(ImageFilter.GaussianBlur(0.32)), outer, 0.82),
        (masks["body"].filter(ImageFilter.GaussianBlur(0.28)), body, 0.84),
        (masks["cyan"].filter(ImageFilter.GaussianBlur(0.24)), inner, 0.82),
        (micro.filter(ImageFilter.GaussianBlur(0.26)), lightning, 0.54),
        (major.filter(ImageFilter.GaussianBlur(0.20)), lightning, 0.88),
        (masks["core"].filter(ImageFilter.GaussianBlur(0.18)), core, 0.82),
    ):
        result = Image.alpha_composite(result, _mask_layer(mask, color, alpha_scale))

    major_white = major.filter(ImageFilter.MinFilter(3))
    result = Image.alpha_composite(result, _mask_layer(major_white, core, 0.44))
    return result


def render_stroke_bundle(
    frame: Image.Image,
    params: dict[str, str | float | int],
    *,
    seed: int,
    frame_index: int,
    frame_count: int,
) -> Image.Image:
    graph = build_energy_graph(frame.size, params, seed=seed, frame_index=frame_index, frame_count=frame_count)
    masks = _render_flow_masks(graph, frame.size, params, seed=seed)
    major, micro = _render_lightning_masks(graph, frame.size, params, seed=seed, frame_index=frame_index)
    return _compose_bundle(frame.size, masks, major, micro, params)


def apply_stroke_bundle_to_frames(
    frame_paths: list[Path],
    params: dict[str, str | float | int],
    *,
    seed: int,
) -> None:
    frame_count = len(frame_paths)
    for frame_index, frame_path in enumerate(frame_paths):
        frame = Image.open(frame_path).convert("RGBA")
        render_stroke_bundle(
            frame,
            params,
            seed=seed,
            frame_index=frame_index,
            frame_count=frame_count,
        ).save(frame_path)
