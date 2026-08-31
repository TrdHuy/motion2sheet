"""Config-driven camera profile loading and validation for anim2sheet review."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SUPPORTED_PROJECTIONS = {"orthographic", "perspective"}
SUPPORTED_ROLES = {"final", "diagnostic"}


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    return float(value)


def _vec3(value: Any, field: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{field} must be a 3-number array")
    return [_number(v, field) for v in value]


def validate_camera_profile(data: Any) -> dict:
    if not isinstance(data, dict):
        raise ValueError("camera profile root must be an object")
    version = data.get("version")
    if not isinstance(version, int) or version < 1:
        raise ValueError("camera profile version must be an integer >= 1")

    cameras = data.get("cameras")
    if not isinstance(cameras, dict) or not cameras:
        raise ValueError("camera profile cameras must be a non-empty object")

    normalized: dict[str, dict] = {}
    for name, raw in cameras.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("camera profile keys must be non-empty strings")
        if not isinstance(raw, dict):
            raise ValueError(f"camera {name} must be an object")

        role = raw.get("role")
        if role not in SUPPORTED_ROLES:
            raise ValueError(
                f"camera {name} role must be one of {sorted(SUPPORTED_ROLES)}, got {role!r}"
            )
        projection = raw.get("projection")
        if projection not in SUPPORTED_PROJECTIONS:
            raise ValueError(
                f"camera {name} projection must be one of "
                f"{sorted(SUPPORTED_PROJECTIONS)}, got {projection!r}"
            )

        row = {
            "name": name,
            "role": role,
            "projection": projection,
            "position": _vec3(raw.get("position"), f"camera {name} position"),
            "rotationDeg": _vec3(raw.get("rotationDeg"), f"camera {name} rotationDeg"),
        }
        if projection == "orthographic":
            scale = _number(raw.get("orthoScale"), f"camera {name} orthoScale")
            if scale <= 0.0:
                raise ValueError(f"camera {name} orthoScale must be > 0")
            row["orthoScale"] = scale
        else:
            focal = _number(raw.get("focalLengthMm"), f"camera {name} focalLengthMm")
            if focal <= 0.0:
                raise ValueError(f"camera {name} focalLengthMm must be > 0")
            row["focalLengthMm"] = focal
        normalized[name] = row

    defaults = data.get("defaultReviewCameras")
    if not isinstance(defaults, list) or not defaults:
        raise ValueError("defaultReviewCameras must be a non-empty array")
    if any(not isinstance(v, str) or not v.strip() for v in defaults):
        raise ValueError("defaultReviewCameras entries must be non-empty strings")
    if len(defaults) != len(set(defaults)):
        raise ValueError("defaultReviewCameras contains duplicate camera names")
    unknown = [name for name in defaults if name not in normalized]
    if unknown:
        raise ValueError(f"defaultReviewCameras contains unknown cameras: {unknown}")

    return {
        "version": version,
        "defaultReviewCameras": list(defaults),
        "cameras": normalized,
    }


def load_camera_profile(path: str | Path) -> dict:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    result = validate_camera_profile(data)
    result["source"] = str(path.resolve())
    return result


def resolve_camera_names(profile: dict, requested: str | None = None) -> list[str]:
    if requested is None:
        names = list(profile["defaultReviewCameras"])
    else:
        names = [value.strip() for value in requested.split(",") if value.strip()]
        if not names:
            raise ValueError("--cameras did not contain any camera names")
    if len(names) != len(set(names)):
        raise ValueError(f"duplicate cameras requested: {names}")
    unknown = [name for name in names if name not in profile["cameras"]]
    if unknown:
        raise ValueError(f"unknown cameras requested: {unknown}")
    return names


def final_camera_name(profile: dict, names: list[str]) -> str | None:
    finals = [name for name in names if profile["cameras"][name]["role"] == "final"]
    if len(finals) > 1:
        raise ValueError(f"multiple final cameras selected: {finals}")
    return finals[0] if finals else None
