from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class EnergyNode:
    u: float
    point: tuple[float, float]
    tangent: tuple[float, float]
    normal: tuple[float, float]
    width: float
    energy: float


@dataclass(frozen=True)
class EnergyGraph:
    nodes: tuple[EnergyNode, ...]
    tail_t: float
    head_t: float
    energy: float
    breakup: float

    def major_anchor_indices(self, count: int, rng: random.Random) -> list[int]:
        if count <= 0 or len(self.nodes) < 8:
            return []
        low = max(2, round(len(self.nodes) * 0.12))
        high = min(len(self.nodes) - 3, round(len(self.nodes) * 0.88))
        span = max(1, high - low)
        result: list[int] = []
        for slot in range(count):
            center = low + span * (slot + 0.5) / count
            jitter = rng.uniform(-0.10, 0.10) * span / max(1, count)
            result.append(max(low, min(high, round(center + jitter))))
        return sorted(set(result))


def smoothstep01(value: float) -> float:
    x = max(0.0, min(1.0, value))
    return x * x * (3.0 - 2.0 * x)


def motion_window(index: int, frames: int, peak_t: float) -> tuple[float, float, float, float]:
    t = index / max(frames - 1, 1)
    if t <= peak_t:
        growth = smoothstep01(t / max(peak_t, 1e-6))
        return 0.075 * growth * growth, 0.10 + 0.90 * growth, 0.55 + 0.45 * growth, 0.0
    decay = smoothstep01((t - peak_t) / max(1e-6, 1.0 - peak_t))
    # The old tail advanced to 0.92 at F8, collapsing every renderer into a
    # tiny star/blob regardless of how fragmentation was implemented. Preserve
    # a residual curved trajectory instead; individual stroke lifetimes now
    # decide which pieces remain visible across that trajectory.
    return 0.075 + 0.50 * decay, 1.0, 1.0 - 0.86 * decay, decay


def normalize(x: float, y: float) -> tuple[float, float]:
    length = math.hypot(x, y)
    if length <= 1e-6:
        return 1.0, 0.0
    return x / length, y / length


def _smoothed_noise(count: int, amplitude: float, smoothness: float, rng: random.Random) -> list[float]:
    values = [rng.uniform(-amplitude, amplitude) for _ in range(count)]
    passes = 2 if smoothness < 0.55 else 3
    for _ in range(passes):
        previous = values[:]
        for index in range(1, count - 1):
            local = previous[index - 1] * 0.25 + previous[index] * 0.50 + previous[index + 1] * 0.25
            values[index] = previous[index] * (1.0 - smoothness) + local * smoothness
    return values


def _graph_center(size: tuple[int, int], params: dict[str, str | float | int]) -> tuple[float, float]:
    return (
        size[0] * (0.5 + float(params["shape.offset_x"])),
        size[1] * (0.5 + float(params["shape.offset_y"])),
    )


def _arc_point(
    size: tuple[int, int],
    params: dict[str, str | float | int],
    canonical_t: float,
    radial_offset_px: float,
) -> tuple[float, float]:
    radius = float(params["radius"])
    angle = math.radians(
        float(params["start_angle"])
        + float(params["arc_angle"]) * canonical_t
        + float(params["rotation"])
    )
    reference_radius = 1.5
    pixel_scale = min(size) / (reference_radius * 3.35)
    nx, ny = math.cos(angle), -math.sin(angle)
    center_x, center_y = _graph_center(size, params)
    x = center_x + radius * math.cos(angle) * pixel_scale + nx * radial_offset_px
    y = center_y - radius * math.sin(angle) * pixel_scale + ny * radial_offset_px
    return x, y


def build_energy_graph(
    size: tuple[int, int],
    params: dict[str, str | float | int],
    *,
    seed: int,
    frame_index: int,
    frame_count: int,
) -> EnergyGraph:
    tail_t, head_t, energy, breakup = motion_window(frame_index, frame_count, float(params["timing.peak"]))
    count = 72
    rng = random.Random(seed * 104729 + frame_index * 7919 + 503)
    radius_scale = float(params["radius"]) / 1.5
    width_jitter = float(params["core.width_jitter"])
    smoothness = float(params["core.width_smoothness"])
    center_jitter = float(params["core.center_jitter"])
    center_frequency = float(params["core.center_frequency"])
    width_noise = _smoothed_noise(count, width_jitter, smoothness, rng)
    center_noise = _smoothed_noise(count, 1.0, min(0.94, smoothness + 0.10), rng)
    phase_a = rng.uniform(0.0, math.tau)
    phase_b = rng.uniform(0.0, math.tau)

    hotspot_count = int(params["core.hotspot_count"])
    hotspot_scale = float(params["core.hotspot_scale"])
    hotspots = [
        (rng.uniform(0.14, 0.88), rng.uniform(0.035, 0.090), rng.uniform(0.28, 0.64) * hotspot_scale)
        for _ in range(hotspot_count)
    ]

    points: list[tuple[float, float]] = []
    widths: list[float] = []
    node_energy: list[float] = []
    width_min = float(params["core.width_min"])
    width_max = float(params["core.width_max"])
    nominal = width_min + (width_max - width_min) * 0.56

    for index in range(count):
        u = index / (count - 1)
        canonical_t = tail_t + (head_t - tail_t) * u
        coherent = (
            math.sin(u * math.tau * center_frequency + phase_a) * 0.62
            + math.sin(u * math.tau * center_frequency * 0.47 + phase_b) * 0.38
        )
        radial = center_jitter * radius_scale * (0.72 * coherent + 0.28 * center_noise[index]) * (0.76 + 0.24 * energy)
        points.append(_arc_point(size, params, canonical_t, radial))

        tail_taper = smoothstep01(u / 0.10)
        head_taper = smoothstep01((1.0 - u) / 0.075)
        envelope = tail_taper * head_taper
        local = 1.0 + width_noise[index]
        hotspot_boost = 0.0
        for center, sigma, amplitude in hotspots:
            hotspot_boost += amplitude * math.exp(-((u - center) ** 2) / max(1e-6, 2.0 * sigma * sigma))
        body_bias = 0.80 + 0.20 * math.sin(math.pi * u)
        width = nominal * radius_scale * body_bias * local * (1.0 + hotspot_boost) * envelope
        width *= (0.72 + 0.28 * energy) * (1.0 - 0.20 * breakup)
        widths.append(max(0.30, width))
        node_energy.append(min(1.0, 0.88 + 0.08 * hotspot_boost + 0.04 * max(0.0, local - 1.0)))

    nodes: list[EnergyNode] = []
    center_x, center_y = _graph_center(size, params)
    for index, point in enumerate(points):
        previous = points[max(0, index - 1)]
        following = points[min(len(points) - 1, index + 1)]
        tx, ty = normalize(following[0] - previous[0], following[1] - previous[1])
        nx, ny = -ty, tx
        if (point[0] - center_x) * nx + (point[1] - center_y) * ny < 0.0:
            nx, ny = -nx, -ny
        nodes.append(EnergyNode(index / (count - 1), point, (tx, ty), (nx, ny), widths[index], node_energy[index]))

    return EnergyGraph(tuple(nodes), tail_t, head_t, energy, breakup)
