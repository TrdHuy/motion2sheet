from __future__ import annotations

from pathlib import Path
from typing import Any

import json5


def _vec3(value: Any, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 3 or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in value):
        raise ValueError(f"{label} must be a numeric vec3")
    return [float(v) for v in value]


def load_camera_profile(path: Path) -> dict[str, Any]:
    data = json5.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("camera profile root must be an object")
    allowed = {"schema", "version", "id", "projection", "location", "target", "upAxis", "orthoScale", "followRoot", "margin"}
    extra = set(data) - allowed
    if extra:
        raise ValueError(f"camera profile contains unknown fields: {sorted(extra)}")
    if data.get("schema") != "motion2sheet.camera" or data.get("version") != 1:
        raise ValueError("unsupported camera profile schema/version")
    if not isinstance(data.get("id"), str) or not data["id"]:
        raise ValueError("camera profile id is required")
    if data.get("projection") != "ORTHO":
        raise ValueError("real model renderer currently supports ORTHO camera only")
    data["location"] = _vec3(data.get("location"), "camera.location")
    data["target"] = _vec3(data.get("target"), "camera.target")
    data["upAxis"] = _vec3(data.get("upAxis"), "camera.upAxis")
    scale = data.get("orthoScale")
    if isinstance(scale, bool) or not isinstance(scale, (int, float)) or float(scale) <= 0:
        raise ValueError("camera.orthoScale must be positive")
    data["orthoScale"] = float(scale)
    if not isinstance(data.get("followRoot"), bool):
        raise ValueError("camera.followRoot must be boolean")
    return data
