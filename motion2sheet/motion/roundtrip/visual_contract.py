from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

PANEL = 256
PADDING = 18
COLUMNS = 8


@dataclass(frozen=True)
class ProjectionConfig:
    min_x: float
    max_y: float
    scale: float


def frame_numbers(data: dict[str, Any]) -> tuple[int, ...]:
    start, end = data["frameRange"]
    frames = tuple(range(int(start), int(end) + 1))
    if not frames:
        raise ValueError("visual pose data has no frames")
    return frames


def project_point(point: Sequence[float]) -> tuple[float, float]:
    x, y, z = (float(value) for value in point)
    return x - 0.42 * y, z + 0.20 * y


def _frame_projected_points(frame: dict[str, Any]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for bone in frame.values():
        points.append(project_point(bone["head"]))
        points.append(project_point(bone["tail"]))
    return points


def projection_config_for_branches(*branches: dict[str, Any]) -> ProjectionConfig:
    """Compute one canonical projection across one or more frame branches."""

    points: list[tuple[float, float]] = []
    for branch in branches:
        for frame in branch.values():
            points.extend(_frame_projected_points(frame))
    if not points:
        raise ValueError("visual pose data has no points")

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = max(max_x - min_x, 1e-9)
    height = max(max_y - min_y, 1e-9)
    scale = min((PANEL - 2 * PADDING) / width, (PANEL - 2 * PADDING) / height)
    return ProjectionConfig(min_x=min_x, max_y=max_y, scale=scale)


def projection_config(data: dict[str, Any]) -> ProjectionConfig:
    return projection_config_for_branches(data["source"], data["reconstructed"])


def panel_pixel(point: Sequence[float], config: ProjectionConfig) -> tuple[int, int]:
    """Map a pose point to the canonical per-frame integer pixel grid."""

    x, y = project_point(point)
    px = PADDING + (x - config.min_x) * config.scale
    py = PADDING + (config.max_y - y) * config.scale
    return int(round(px)), int(round(py))


def panel_origin(index: int) -> tuple[int, int]:
    if index < 0:
        raise ValueError("visual panel index must be non-negative")
    return (index % COLUMNS) * PANEL, (index // COLUMNS) * PANEL


def panel_box(index: int) -> tuple[int, int, int, int]:
    x, y = panel_origin(index)
    return x, y, x + PANEL, y + PANEL


def sheet_pixel(index: int, point: Sequence[float], config: ProjectionConfig) -> tuple[int, int]:
    panel_x, panel_y = panel_origin(index)
    point_x, point_y = panel_pixel(point, config)
    return panel_x + point_x, panel_y + point_y


def sheet_size(frame_count: int) -> tuple[int, int]:
    if frame_count <= 0:
        raise ValueError("visual sheet frame count must be positive")
    rows = math.ceil(frame_count / COLUMNS)
    return PANEL * COLUMNS, PANEL * rows
