from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import json5


def validate_trajectory_config(value: Any) -> dict[str, Any] | None:
    """Validate orchestration data only; trajectory sampling stays Blender-native."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("trajectory config must be an object")

    trajectory_type = str(value.get("type", "points")).strip().lower()
    if trajectory_type != "points":
        raise ValueError(f"Unsupported trajectory type: {trajectory_type}")

    interpolation = str(value.get("interpolation", "catmull-rom")).strip().lower()
    if interpolation != "catmull-rom":
        raise ValueError(f"Unsupported trajectory interpolation: {interpolation}")

    closed = value.get("closed", False)
    if not isinstance(closed, bool):
        raise ValueError("trajectory.closed must be boolean")
    if closed:
        raise ValueError("trajectory.closed=true is not supported yet")

    raw_points = value.get("points")
    if not isinstance(raw_points, (list, tuple)):
        raise ValueError("trajectory.points must be an array of [x, y] points")
    if len(raw_points) < 2:
        raise ValueError("trajectory.points must contain at least 2 points")
    if len(raw_points) > 128:
        raise ValueError("trajectory.points supports at most 128 points")

    points: list[list[float]] = []
    total_length = 0.0
    previous: tuple[float, float] | None = None
    for index, raw_point in enumerate(raw_points):
        if not isinstance(raw_point, (list, tuple)) or len(raw_point) != 2:
            raise ValueError(f"trajectory.points[{index}] must be [x, y]")
        try:
            x, y = float(raw_point[0]), float(raw_point[1])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"trajectory.points[{index}] coordinates must be numeric") from exc
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError(f"trajectory.points[{index}] coordinates must be finite")
        if abs(x) > 1000.0 or abs(y) > 1000.0:
            raise ValueError(f"trajectory.points[{index}] coordinates are unreasonably large")
        if previous is not None:
            segment = math.hypot(x - previous[0], y - previous[1])
            if segment <= 1e-6:
                raise ValueError(f"trajectory.points[{index}] duplicates the previous point")
            total_length += segment
        points.append([x, y])
        previous = (x, y)

    if total_length <= 1e-5:
        raise ValueError("trajectory.points total path length is too small")

    return {
        "type": "points",
        "points": points,
        "interpolation": "catmull-rom",
        "closed": False,
    }


def load_trajectory_config(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
        data = json5.loads(text) if path.suffix.lower() == ".json5" else json.loads(text)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Unable to read trajectory config {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("trajectory config root must be an object")
    # Accept either a direct trajectory object or { trajectory: {...} } so the
    # same file can later grow into a broader generation config without changing CLI.
    candidate = data.get("trajectory", data)
    validated = validate_trajectory_config(candidate)
    assert validated is not None
    return validated
