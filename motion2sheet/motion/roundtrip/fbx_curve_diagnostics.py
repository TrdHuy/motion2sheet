from __future__ import annotations

import math
from typing import Any


def validate_fbx_curve_samples(
    key_times: list[int],
    key_values: list[float],
    *,
    label: str,
) -> None:
    if len(key_times) != len(key_values) or not key_times:
        raise RuntimeError(f"FBX animation curve {label!r} has invalid key arrays")
    if any(right <= left for left, right in zip(key_times, key_times[1:])):
        raise RuntimeError(f"FBX animation curve {label!r} has non-increasing KeyTime values")
    if not all(math.isfinite(value) for value in key_values):
        raise RuntimeError(f"FBX animation curve {label!r} contains non-finite values")


def complete_missing_transform_curve_diagnostics(
    source_curves: list[dict[str, Any]],
    bone_stacks: dict[str, dict[str, Any]],
    sample_key_times: list[int],
) -> list[dict[str, Any]]:
    """Preserve raw curves and synthesize only channels absent from the FBX."""

    result = [
        {
            **curve,
            "keyTimes": list(curve["keyTimes"]),
            "keyValues": list(curve["keyValues"]),
        }
        for curve in source_curves
    ]
    curve_map: dict[tuple[str, str, str], dict[str, Any]] = {}
    for curve in result:
        validate_fbx_curve_samples(
            curve["keyTimes"],
            curve["keyValues"],
            label=f"{curve['bone']} {curve['property']}.{curve['axis']}",
        )
        key = (curve["bone"], curve["property"], curve["axis"])
        if key in curve_map:
            raise RuntimeError(f"POC v1 does not support multiple FBX curves for {key[0]} {key[1]}.{key[2]}")
        curve_map[key] = curve

    stack_field_by_property = {
        "translation": "Lcl Translation",
        "rotation": "Lcl Rotation",
        "scale": "Lcl Scaling",
    }
    for bone_name, stack in bone_stacks.items():
        for property_name, stack_field in stack_field_by_property.items():
            defaults = stack[stack_field]
            for axis_index, axis_name in enumerate(("x", "y", "z")):
                key = (bone_name, property_name, axis_name)
                if key in curve_map:
                    continue
                curve = {
                    "bone": bone_name,
                    "property": property_name,
                    "axis": axis_name,
                    "keyTimes": list(sample_key_times),
                    "keyValues": [float(defaults[axis_index])] * len(sample_key_times),
                }
                result.append(curve)
                curve_map[key] = curve
    return sorted(result, key=lambda item: (item["bone"], item["property"], item["axis"]))
