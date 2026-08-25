from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import json5


def _finite_number(value: Any, label: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{label} must be finite")
    if abs(parsed) > 1000.0:
        raise ValueError(f"{label} is unreasonably large")
    return parsed


def _validate_scale(value: Any) -> dict[str, float] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("trajectory.scale must be an object")
    start = _finite_number(value.get("start", 1.0), "trajectory.scale.start")
    end = _finite_number(value.get("end", 1.0), "trajectory.scale.end")
    if start <= 0.0 or end <= 0.0:
        raise ValueError("trajectory.scale values must be greater than zero")
    if start > 8.0 or end > 8.0:
        raise ValueError("trajectory.scale values must be <= 8")
    return {"start": start, "end": end}


def _validate_points(value: dict[str, Any]) -> dict[str, Any]:
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
        raise ValueError("trajectory.points must be an array of [x, y] or [x, y, z] points")
    if len(raw_points) < 2:
        raise ValueError("trajectory.points must contain at least 2 points")
    if len(raw_points) > 128:
        raise ValueError("trajectory.points supports at most 128 points")

    explicit_dimensions = value.get("dimensions")
    if explicit_dimensions is not None:
        try:
            dimensions = int(explicit_dimensions)
        except (TypeError, ValueError) as exc:
            raise ValueError("trajectory.dimensions must be 2 or 3") from exc
        if dimensions not in (2, 3):
            raise ValueError("trajectory.dimensions must be 2 or 3")
    else:
        first = raw_points[0]
        if not isinstance(first, (list, tuple)) or len(first) not in (2, 3):
            raise ValueError("trajectory.points[0] must be [x, y] or [x, y, z]")
        dimensions = len(first)

    points: list[list[float]] = []
    total_length = 0.0
    previous: tuple[float, ...] | None = None
    for index, raw_point in enumerate(raw_points):
        if not isinstance(raw_point, (list, tuple)) or len(raw_point) != dimensions:
            raise ValueError(f"trajectory.points[{index}] must contain exactly {dimensions} coordinates")
        point = tuple(_finite_number(raw_point[axis], f"trajectory.points[{index}][{axis}]") for axis in range(dimensions))
        if previous is not None:
            segment = math.sqrt(sum((point[axis] - previous[axis]) ** 2 for axis in range(dimensions)))
            if segment <= 1e-6:
                raise ValueError(f"trajectory.points[{index}] duplicates the previous point")
            total_length += segment
        points.append(list(point))
        previous = point

    if total_length <= 1e-5:
        raise ValueError("trajectory.points total path length is too small")

    result: dict[str, Any] = {
        "type": "points",
        "dimensions": dimensions,
        "points": points,
        "interpolation": "catmull-rom",
        "closed": False,
    }
    scale = _validate_scale(value.get("scale"))
    if scale is not None:
        result["scale"] = scale
    return result


def _validate_conical_helix(value: dict[str, Any]) -> dict[str, Any]:
    interpolation = str(value.get("interpolation", "catmull-rom")).strip().lower()
    if interpolation != "catmull-rom":
        raise ValueError(f"Unsupported trajectory interpolation: {interpolation}")
    closed = value.get("closed", False)
    if closed not in (False, None):
        raise ValueError("conical-helix trajectory cannot be closed")

    turns = _finite_number(value.get("turns", 2.25), "trajectory.turns")
    bottom = _finite_number(value.get("bottom", -0.95), "trajectory.bottom")
    top = _finite_number(value.get("top", 1.05), "trajectory.top")
    radius_start = _finite_number(value.get("radiusStart", 1.05), "trajectory.radiusStart")
    radius_end = _finite_number(value.get("radiusEnd", 0.12), "trajectory.radiusEnd")
    phase_degrees = _finite_number(value.get("phaseDegrees", 0.0), "trajectory.phaseDegrees")
    try:
        samples = int(value.get("samples", 24))
    except (TypeError, ValueError) as exc:
        raise ValueError("trajectory.samples must be an integer") from exc

    if turns <= 0.0 or turns > 20.0:
        raise ValueError("trajectory.turns must be > 0 and <= 20")
    if top <= bottom:
        raise ValueError("trajectory.top must be greater than trajectory.bottom")
    if radius_start <= 0.0 or radius_end < 0.0:
        raise ValueError("trajectory radii must be non-negative and radiusStart must be > 0")
    if radius_start > 20.0 or radius_end > 20.0:
        raise ValueError("trajectory radii must be <= 20")
    if samples < 4 or samples > 128:
        raise ValueError("trajectory.samples must be between 4 and 128")

    result: dict[str, Any] = {
        "type": "conical-helix",
        "dimensions": 3,
        "interpolation": "catmull-rom",
        "closed": False,
        "turns": turns,
        "bottom": bottom,
        "top": top,
        "radiusStart": radius_start,
        "radiusEnd": radius_end,
        "phaseDegrees": phase_degrees,
        "samples": samples,
    }
    scale = _validate_scale(value.get("scale"))
    if scale is not None:
        result["scale"] = scale
    return result


def validate_trajectory_config(value: Any) -> dict[str, Any] | None:
    """Validate orchestration data only; trajectory sampling stays Blender-native."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("trajectory config must be an object")

    trajectory_type = str(value.get("type", "points")).strip().lower()
    if trajectory_type == "points":
        return _validate_points(value)
    if trajectory_type == "conical-helix":
        return _validate_conical_helix(value)
    raise ValueError(f"Unsupported trajectory type: {trajectory_type}")


def load_trajectory_config(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
        data = json5.loads(text) if path.suffix.lower() == ".json5" else json.loads(text)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Unable to read trajectory config {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("trajectory config root must be an object")
    candidate = data.get("trajectory", data)
    validated = validate_trajectory_config(candidate)
    assert validated is not None
    return validated
