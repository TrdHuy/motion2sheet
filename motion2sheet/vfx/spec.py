from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SLASH_VARIANTS = {
    "lightning": {
        "radius": 1.5,
        "arc_angle": 150.0,
        "thickness": 0.12,
        "core.intensity": 9.0,
        "glow.intensity": 3.4,
        "sparks.count": 22,
        "sparks.spread": 0.30,
        "sparks.size": 0.040,
        "lightning.jitter": 0.11,
        "lightning.branches": 8,
        "lightning.length": 0.30,
        "shape.body_scale": 2.8,
        "shape.inner_scale": 1.58,
        "shape.core_scale": 0.52,
        "shape.edge_noise": 0.78,
        "shape.taper_power": 0.55,
        "shape.flare": 0.34,
        "fragments.count": 18,
        "fragments.spread": 0.42,
        "fragments.size": 0.080,
        "timing.peak": 0.57,
        "timing.decay": 0.72,
        "start_angle": -75.0,
        "rotation": 0.0,
        "fade_in": 0.25,
        "fade_out": 0.45,
    }
}

PARAM_RANGES: dict[str, tuple[float, float]] = {
    "radius": (0.1, 10.0),
    "arc_angle": (10.0, 340.0),
    "thickness": (0.01, 1.0),
    "core.intensity": (0.0, 100.0),
    "glow.intensity": (0.0, 100.0),
    "sparks.count": (0.0, 500.0),
    "sparks.spread": (0.0, 3.0),
    "sparks.size": (0.001, 1.0),
    "lightning.jitter": (0.0, 1.0),
    "lightning.branches": (0.0, 100.0),
    "lightning.length": (0.01, 3.0),
    "shape.body_scale": (0.2, 8.0),
    "shape.inner_scale": (0.1, 8.0),
    "shape.core_scale": (0.05, 4.0),
    "shape.edge_noise": (0.0, 3.0),
    "shape.taper_power": (0.1, 3.0),
    "shape.flare": (0.0, 2.0),
    "fragments.count": (0.0, 300.0),
    "fragments.spread": (0.0, 3.0),
    "fragments.size": (0.001, 1.0),
    "timing.peak": (0.25, 0.80),
    "timing.decay": (0.45, 0.95),
    "start_angle": (-720.0, 720.0),
    "rotation": (-720.0, 720.0),
    "fade_in": (0.0, 1.0),
    "fade_out": (0.0, 1.0),
}

INTEGER_PARAMS = {"sparks.count", "lightning.branches", "fragments.count"}


def parse_set(value: str) -> tuple[str, float]:
    if "=" not in value:
        raise ValueError(f"--set must look like key=value, got {value!r}")
    key, raw = value.split("=", 1)
    key = key.strip()
    if key not in PARAM_RANGES:
        raise ValueError(f"Unknown VFX parameter: {key}")
    try:
        parsed = float(raw)
    except ValueError as exc:
        raise ValueError(f"VFX parameter {key!r} must be numeric") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"VFX parameter {key!r} must be finite")
    if key in INTEGER_PARAMS:
        if not parsed.is_integer():
            raise ValueError(f"VFX parameter {key!r} must be an integer")
        parsed = int(parsed)
    return key, parsed


def _validate_params(params: dict[str, Any]) -> dict[str, float | int]:
    unknown = sorted(set(params) - set(PARAM_RANGES))
    if unknown:
        raise ValueError(f"Unknown VFX parameters: {', '.join(unknown)}")
    result: dict[str, float | int] = {}
    for key, (minimum, maximum) in PARAM_RANGES.items():
        if key not in params:
            raise ValueError(f"Missing VFX parameter: {key}")
        try:
            value = float(params[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"VFX parameter {key!r} must be numeric") from exc
        if not math.isfinite(value) or not minimum <= value <= maximum:
            raise ValueError(f"VFX parameter {key!r} must be in range [{minimum}, {maximum}]")
        if key in INTEGER_PARAMS:
            if not value.is_integer():
                raise ValueError(f"VFX parameter {key!r} must be an integer")
            result[key] = int(value)
        else:
            result[key] = value
    if float(result["timing.decay"]) <= float(result["timing.peak"]):
        raise ValueError("timing.decay must be greater than timing.peak")
    if float(result["shape.core_scale"]) >= float(result["shape.inner_scale"]):
        raise ValueError("shape.core_scale must be smaller than shape.inner_scale")
    if float(result["shape.inner_scale"]) >= float(result["shape.body_scale"]):
        raise ValueError("shape.inner_scale must be smaller than shape.body_scale")
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
    params: dict[str, float | int]

    @classmethod
    def create(
        cls,
        *,
        template: str,
        variant: str,
        frames: int,
        fps: int,
        canvas: tuple[int, int],
        sheet_columns: int,
        seed: int,
        overrides: list[str] | None = None,
    ) -> "VfxSpec":
        if template != "slash":
            raise ValueError(f"Unsupported VFX template: {template}")
        if variant not in SLASH_VARIANTS:
            raise ValueError(f"Unsupported slash variant: {variant}")
        params = dict(SLASH_VARIANTS[variant])
        for override in overrides or []:
            key, value = parse_set(override)
            params[key] = value
        return cls(
            template=template,
            variant=variant,
            frames=frames,
            fps=fps,
            canvas=canvas,
            sheet_columns=sheet_columns,
            seed=seed,
            params=_validate_params(params),
        ).validated()

    def validated(self) -> "VfxSpec":
        if self.template != "slash":
            raise ValueError(f"Unsupported VFX template: {self.template}")
        if self.variant not in SLASH_VARIANTS:
            raise ValueError(f"Unsupported slash variant: {self.variant}")
        if self.frames < 2 or self.frames > 120:
            raise ValueError("frames must be between 2 and 120")
        if self.fps <= 0 or self.fps > 240:
            raise ValueError("fps must be between 1 and 240")
        if self.canvas[0] <= 0 or self.canvas[1] <= 0:
            raise ValueError("canvas dimensions must be positive")
        if self.sheet_columns <= 0 or self.sheet_columns > self.frames:
            raise ValueError("sheet-columns must be between 1 and frame count")
        if self.seed < 0 or self.seed > 2**31 - 1:
            raise ValueError("seed must be between 0 and 2147483647")
        _validate_params(self.params)
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": 1,
            "template": self.template,
            "variant": self.variant,
            "frames": self.frames,
            "fps": self.fps,
            "canvas": [self.canvas[0], self.canvas[1]],
            "sheetColumns": self.sheet_columns,
            "seed": self.seed,
            "params": dict(self.params),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VfxSpec":
        if int(data.get("schemaVersion", 1)) != 1:
            raise ValueError("Unsupported VFX spec schemaVersion")
        canvas = data["canvas"]
        return cls(
            template=str(data["template"]),
            variant=str(data["variant"]),
            frames=int(data["frames"]),
            fps=int(data["fps"]),
            canvas=(int(canvas[0]), int(canvas[1])),
            sheet_columns=int(data["sheetColumns"]),
            seed=int(data["seed"]),
            params=_validate_params(dict(data["params"])),
        ).validated()

    @classmethod
    def load(cls, path: Path) -> "VfxSpec":
        try:
            return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ValueError(f"Unable to read VFX spec {path}: {exc}") from exc
