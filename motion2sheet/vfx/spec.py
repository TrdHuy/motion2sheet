from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BUILD_DEFAULTS = {"frames": 8, "fps": 12, "canvas": (512, 512), "sheet_columns": 4, "seed": 42891}

SLASH_VARIANTS: dict[str, dict[str, Any]] = {
    "lightning": {
        "radius": 1.5, "arc_angle": 150.0, "thickness": 0.12,
        "colors.outer": "#0018D8", "colors.body": "#0048FF", "colors.inner": "#00A8FF", "colors.core": "#FFFFFF", "colors.lightning": "#9CEEFF",
        "intensity.outer": 0.75, "intensity.body": 0.95, "intensity.inner": 1.25, "intensity.core": 4.0, "intensity.lightning": 3.8,
        "glow.outer_radius": 18.0, "glow.inner_radius": 8.0, "glow.core_radius": 3.0,
        "glow.outer_strength": 0.55, "glow.inner_strength": 0.34, "glow.core_strength": 0.22,
        "energy.body_floor": 0.26, "energy.body_gain": 0.94,
        "energy.cyan_threshold": 0.69, "energy.white_threshold": 0.88,
        "energy.turbulence": 0.055, "energy.turbulence_frequency": 5.4,
        "energy.core_gain": 1.0, "energy.lightning_gain": 1.0,
        "energy.root_width_coupling": 0.70,
        "energy.alpha_power": 1.08, "energy.alpha_gain": 0.94, "energy.base_alpha_mix": 0.70,
        "energy.glow_radius": 8.0, "energy.glow_strength": 0.62,
        "core.width_min": 3.8, "core.width_max": 8.6, "core.width_jitter": 0.42, "core.width_smoothness": 0.70,
        "core.center_jitter": 3.2, "core.center_frequency": 4.8, "core.streak_count": 3,
        "core.streak_width_ratio": 0.30, "core.split_probability": 0.38, "core.hotspot_count": 4, "core.hotspot_scale": 1.15,
        "sparks.count": 40, "sparks.spread": 0.55, "sparks.size": 0.042,
        "lightning.jitter": 0.38, "lightning.branch_count": 24, "lightning.secondary_branch_count": 18,
        "lightning.surface_crack_count": 18, "lightning.length": 0.58, "lightning.spread": 0.75,
        "lightning.width": 1.55, "lightning.secondary_width": 0.90, "lightning.surface_width": 0.80,
        "lightning.edge_bias": 0.92, "lightning.cluster_strength": 0.62,
        "lightning.major_count": 4, "lightning.major_width_min": 2.2, "lightning.major_width_max": 4.8,
        "lightning.tip_width": 0.35, "lightning.width_jitter": 0.34, "lightning.width_smoothness": 0.72,
        "lightning.taper_power": 1.35, "lightning.branch_probability": 0.52, "lightning.branch_depth": 2,
        "lightning.minor_width_ratio": 0.46, "lightning.minor_length_ratio": 0.48,
        "lightning.micro_count": 22, "lightning.micro_width": 0.75, "lightning.micro_intensity": 0.34,
        "lightning.glow_radius": 4.5, "lightning.glow_strength": 0.48,
        "shape.body_scale": 3.30, "shape.inner_scale": 1.35, "shape.core_scale": 0.18,
        "shape.form_noise": 0.52, "shape.form_noise_frequency": 2.4,
        "shape.edge_noise": 1.60, "shape.edge_noise_frequency": 12.0,
        "shape.detail_noise": 0.42, "shape.detail_noise_frequency": 24.0,
        "shape.taper_power": 0.50, "shape.flare": 0.50,
        "shape.tongue_count": 16, "shape.tongue_length": 0.58, "shape.tongue_curve": 0.85, "shape.tongue_width": 0.72,
        "fragments.count": 30, "fragments.spread": 0.58, "fragments.size": 0.075,
        "timing.peak": 0.57, "timing.decay": 0.68,
        "start_angle": -75.0, "rotation": 0.0, "fade_in": 0.25, "fade_out": 0.45,
    }
}

PARAM_RANGES: dict[str, tuple[float, float]] = {
    "radius": (0.1, 10.0), "arc_angle": (10.0, 340.0), "thickness": (0.01, 1.0),
    "intensity.outer": (0.0, 100.0), "intensity.body": (0.0, 100.0), "intensity.inner": (0.0, 100.0), "intensity.core": (0.0, 100.0), "intensity.lightning": (0.0, 100.0),
    "glow.outer_radius": (0.0, 64.0), "glow.inner_radius": (0.0, 64.0), "glow.core_radius": (0.0, 32.0),
    "glow.outer_strength": (0.0, 2.0), "glow.inner_strength": (0.0, 2.0), "glow.core_strength": (0.0, 2.0),
    "energy.body_floor": (0.0, 1.0), "energy.body_gain": (0.1, 2.0),
    "energy.cyan_threshold": (0.40, 0.90), "energy.white_threshold": (0.60, 0.99),
    "energy.turbulence": (0.0, 0.25), "energy.turbulence_frequency": (0.25, 24.0),
    "energy.core_gain": (0.1, 2.0), "energy.lightning_gain": (0.1, 2.0),
    "energy.root_width_coupling": (0.1, 1.5),
    "energy.alpha_power": (0.4, 3.0), "energy.alpha_gain": (0.1, 1.5), "energy.base_alpha_mix": (0.0, 1.0),
    "energy.glow_radius": (0.0, 32.0), "energy.glow_strength": (0.0, 2.0),
    "core.width_min": (0.2, 24.0), "core.width_max": (0.2, 32.0), "core.width_jitter": (0.0, 0.95), "core.width_smoothness": (0.0, 1.0),
    "core.center_jitter": (0.0, 16.0), "core.center_frequency": (0.25, 16.0), "core.streak_count": (0.0, 12.0),
    "core.streak_width_ratio": (0.05, 1.0), "core.split_probability": (0.0, 1.0), "core.hotspot_count": (0.0, 16.0), "core.hotspot_scale": (0.1, 3.0),
    "sparks.count": (0.0, 500.0), "sparks.spread": (0.0, 3.0), "sparks.size": (0.001, 1.0),
    "lightning.jitter": (0.0, 1.5), "lightning.branch_count": (0.0, 100.0), "lightning.secondary_branch_count": (0.0, 300.0),
    "lightning.surface_crack_count": (0.0, 300.0), "lightning.length": (0.01, 3.0), "lightning.spread": (0.0, 3.0),
    "lightning.width": (0.1, 5.0), "lightning.secondary_width": (0.1, 5.0), "lightning.surface_width": (0.1, 5.0),
    "lightning.edge_bias": (0.0, 1.5), "lightning.cluster_strength": (0.0, 1.0),
    "lightning.major_count": (0.0, 24.0), "lightning.major_width_min": (0.1, 16.0), "lightning.major_width_max": (0.1, 20.0),
    "lightning.tip_width": (0.05, 4.0), "lightning.width_jitter": (0.0, 0.9), "lightning.width_smoothness": (0.0, 1.0),
    "lightning.taper_power": (0.2, 4.0), "lightning.branch_probability": (0.0, 1.0), "lightning.branch_depth": (0.0, 3.0),
    "lightning.minor_width_ratio": (0.1, 0.9), "lightning.minor_length_ratio": (0.1, 0.9),
    "lightning.micro_count": (0.0, 200.0), "lightning.micro_width": (0.1, 4.0), "lightning.micro_intensity": (0.0, 1.0),
    "lightning.glow_radius": (0.0, 16.0), "lightning.glow_strength": (0.0, 2.0),
    "shape.body_scale": (0.2, 8.0), "shape.inner_scale": (0.1, 8.0), "shape.core_scale": (0.05, 4.0),
    "shape.form_noise": (0.0, 2.0), "shape.form_noise_frequency": (0.25, 12.0),
    "shape.edge_noise": (0.0, 3.0), "shape.edge_noise_frequency": (0.5, 40.0),
    "shape.detail_noise": (0.0, 2.0), "shape.detail_noise_frequency": (1.0, 80.0),
    "shape.taper_power": (0.1, 3.0), "shape.flare": (0.0, 2.0),
    "shape.tongue_count": (0.0, 50.0), "shape.tongue_length": (0.0, 3.0), "shape.tongue_curve": (0.0, 2.0), "shape.tongue_width": (0.1, 2.0),
    "fragments.count": (0.0, 300.0), "fragments.spread": (0.0, 3.0), "fragments.size": (0.001, 1.0),
    "timing.peak": (0.25, 0.80), "timing.decay": (0.45, 0.95),
    "start_angle": (-720.0, 720.0), "rotation": (-720.0, 720.0), "fade_in": (0.0, 1.0), "fade_out": (0.0, 1.0),
}

COLOR_PARAMS = {"colors.outer", "colors.body", "colors.inner", "colors.core", "colors.lightning"}
INTEGER_PARAMS = {
    "sparks.count", "core.streak_count", "core.hotspot_count",
    "lightning.branch_count", "lightning.secondary_branch_count", "lightning.surface_crack_count",
    "lightning.major_count", "lightning.branch_depth", "lightning.micro_count", "shape.tongue_count", "fragments.count",
}
PARAM_ALIASES = {"core.intensity": "intensity.core", "glow.intensity": "intensity.outer", "lightning.branches": "lightning.branch_count"}
PROFILE_PARAM_GROUPS = {"colors", "intensity", "glow", "energy", "core", "sparks", "lightning", "shape", "fragments", "timing"}
_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def canonical_param_key(key: str) -> str:
    return PARAM_ALIASES.get(key, key)


def parse_param(key: str, raw: Any) -> tuple[str, str | float | int]:
    key = canonical_param_key(key.strip())
    if key in COLOR_PARAMS:
        value = str(raw).strip().upper()
        if not _HEX_COLOR.fullmatch(value):
            raise ValueError(f"VFX parameter {key!r} must be a #RRGGBB color")
        return key, value
    if key not in PARAM_RANGES:
        raise ValueError(f"Unknown VFX parameter: {key}")
    try:
        parsed = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"VFX parameter {key!r} must be numeric") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"VFX parameter {key!r} must be finite")
    minimum, maximum = PARAM_RANGES[key]
    if not minimum <= parsed <= maximum:
        raise ValueError(f"VFX parameter {key!r} must be in range [{minimum}, {maximum}]")
    if key in INTEGER_PARAMS:
        if not parsed.is_integer():
            raise ValueError(f"VFX parameter {key!r} must be an integer")
        return key, int(parsed)
    return key, parsed


def parse_set(value: str) -> tuple[str, str | float | int]:
    if "=" not in value:
        raise ValueError(f"--set must look like key=value, got {value!r}")
    key, raw = value.split("=", 1)
    return parse_param(key, raw)


def _flatten_mapping(prefix: str, value: Any, result: dict[str, Any]) -> None:
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            _flatten_mapping(f"{prefix}.{child_key}" if prefix else str(child_key), child_value, result)
    else:
        result[prefix] = value


def profile_params(profile: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    params = profile.get("params")
    if params is not None:
        if not isinstance(params, dict):
            raise ValueError("profile params must be an object")
        for key, value in params.items():
            if isinstance(value, dict):
                _flatten_mapping(str(key), value, result)
            else:
                result[str(key)] = value
    for group in PROFILE_PARAM_GROUPS:
        if group in profile:
            value = profile[group]
            if not isinstance(value, dict):
                raise ValueError(f"profile {group} must be an object")
            _flatten_mapping(group, value, result)
    for key in ("radius", "arc_angle", "thickness", "start_angle", "rotation", "fade_in", "fade_out"):
        if key in profile:
            result[key] = profile[key]
    return result


def load_profile(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read VFX profile {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("VFX profile root must be an object")
    return data


def parse_profile_canvas(value: Any) -> tuple[int, int]:
    if isinstance(value, str):
        pieces = value.lower().split("x", 1)
        if len(pieces) != 2:
            raise ValueError("profile canvas must look like 512x512 or [512, 512]")
        canvas = int(pieces[0]), int(pieces[1])
    elif isinstance(value, (list, tuple)) and len(value) == 2:
        canvas = int(value[0]), int(value[1])
    else:
        raise ValueError("profile canvas must look like 512x512 or [512, 512]")
    if canvas[0] <= 0 or canvas[1] <= 0:
        raise ValueError("canvas dimensions must be positive")
    return canvas


def _validate_params(params: dict[str, Any]) -> dict[str, str | float | int]:
    canonical: dict[str, Any] = {}
    for raw_key, raw_value in params.items():
        key = canonical_param_key(str(raw_key))
        if key in canonical and raw_key != key:
            raise ValueError(f"Duplicate VFX parameter through alias: {raw_key}")
        canonical[key] = raw_value
    expected = set(PARAM_RANGES) | COLOR_PARAMS
    unknown = sorted(set(canonical) - expected)
    if unknown:
        raise ValueError(f"Unknown VFX parameters: {', '.join(unknown)}")
    missing = sorted(expected - set(canonical))
    if missing:
        raise ValueError(f"Missing VFX parameter: {missing[0]}")
    result: dict[str, str | float | int] = {}
    for key in sorted(expected):
        parsed_key, parsed_value = parse_param(key, canonical[key])
        result[parsed_key] = parsed_value
    if float(result["timing.decay"]) <= float(result["timing.peak"]):
        raise ValueError("timing.decay must be greater than timing.peak")
    if float(result["shape.core_scale"]) >= float(result["shape.inner_scale"]):
        raise ValueError("shape.core_scale must be smaller than shape.inner_scale")
    if float(result["shape.inner_scale"]) >= float(result["shape.body_scale"]):
        raise ValueError("shape.inner_scale must be smaller than shape.body_scale")
    if float(result["lightning.major_width_min"]) > float(result["lightning.major_width_max"]):
        raise ValueError("lightning.major_width_min must be <= lightning.major_width_max")
    if float(result["lightning.tip_width"]) >= float(result["lightning.major_width_max"]):
        raise ValueError("lightning.tip_width must be smaller than lightning.major_width_max")
    if float(result["core.width_min"]) > float(result["core.width_max"]):
        raise ValueError("core.width_min must be <= core.width_max")
    if float(result["energy.cyan_threshold"]) >= float(result["energy.white_threshold"]):
        raise ValueError("energy.cyan_threshold must be smaller than energy.white_threshold")
    return result


@dataclass(frozen=True)
class VfxSpec:
    template: str
    variant: str
    frames: int
    fps: int
    canvas: tuple[int, int]
    sheet_columns: int
    seed: int
    params: dict[str, str | float | int]

    @classmethod
    def create(cls, *, template: str | None = None, variant: str | None = None, frames: int | None = None, fps: int | None = None, canvas: tuple[int, int] | None = None, sheet_columns: int | None = None, seed: int | None = None, overrides: list[str] | None = None, profile: dict[str, Any] | None = None) -> "VfxSpec":
        profile = profile or {}
        resolved_template = template or profile.get("template")
        resolved_variant = variant or profile.get("variant")
        if resolved_template != "slash":
            raise ValueError(f"Unsupported VFX template: {resolved_template}")
        if resolved_variant not in SLASH_VARIANTS:
            raise ValueError(f"Unsupported slash variant: {resolved_variant}")
        params: dict[str, Any] = dict(SLASH_VARIANTS[str(resolved_variant)])
        for key, value in profile_params(profile).items():
            parsed_key, parsed_value = parse_param(key, value)
            params[parsed_key] = parsed_value
        for override in overrides or []:
            key, value = parse_set(override)
            params[key] = value
        resolved_canvas = canvas if canvas is not None else parse_profile_canvas(profile.get("canvas", BUILD_DEFAULTS["canvas"]))
        resolved_frames = int(frames if frames is not None else profile.get("frames", BUILD_DEFAULTS["frames"]))
        resolved_fps = int(fps if fps is not None else profile.get("fps", BUILD_DEFAULTS["fps"]))
        resolved_columns = int(sheet_columns if sheet_columns is not None else profile.get("sheetColumns", profile.get("sheet_columns", BUILD_DEFAULTS["sheet_columns"])))
        resolved_seed = int(seed if seed is not None else profile.get("seed", BUILD_DEFAULTS["seed"]))
        return cls(template=str(resolved_template), variant=str(resolved_variant), frames=resolved_frames, fps=resolved_fps, canvas=resolved_canvas, sheet_columns=resolved_columns, seed=resolved_seed, params=_validate_params(params)).validated()

    def validated(self) -> "VfxSpec":
        if self.template != "slash": raise ValueError(f"Unsupported VFX template: {self.template}")
        if self.variant not in SLASH_VARIANTS: raise ValueError(f"Unsupported slash variant: {self.variant}")
        if self.frames < 2 or self.frames > 120: raise ValueError("frames must be between 2 and 120")
        if self.fps <= 0 or self.fps > 240: raise ValueError("fps must be between 1 and 240")
        if self.canvas[0] <= 0 or self.canvas[1] <= 0: raise ValueError("canvas dimensions must be positive")
        if self.sheet_columns <= 0 or self.sheet_columns > self.frames: raise ValueError("sheet-columns must be between 1 and frame count")
        if self.seed < 0 or self.seed > 2**31 - 1: raise ValueError("seed must be between 0 and 2147483647")
        _validate_params(self.params)
        return self

    def to_dict(self) -> dict[str, Any]:
        return {"schemaVersion": 1, "template": self.template, "variant": self.variant, "frames": self.frames, "fps": self.fps, "canvas": list(self.canvas), "sheetColumns": self.sheet_columns, "seed": self.seed, "params": dict(self.params)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VfxSpec":
        if int(data.get("schemaVersion", 1)) != 1: raise ValueError("Unsupported VFX spec schemaVersion")
        canvas = data["canvas"]
        return cls(template=str(data["template"]), variant=str(data["variant"]), frames=int(data["frames"]), fps=int(data["fps"]), canvas=(int(canvas[0]), int(canvas[1])), sheet_columns=int(data["sheetColumns"]), seed=int(data["seed"]), params=_validate_params(dict(data["params"]))).validated()

    @classmethod
    def load(cls, path: Path) -> "VfxSpec":
        try:
            return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ValueError(f"Unable to read VFX spec {path}: {exc}") from exc
