from __future__ import annotations

import math
from typing import Any

from .schema import ROOT_TRANSLATION_TOLERANCE


def humanoid_root_motion(animation: dict[str, Any]) -> dict[str, Any]:
    translations = animation["root"]["translations"]
    start = [float(value) for value in translations[0]]
    end = [float(value) for value in translations[-1]]
    delta = [end[index] - start[index] for index in range(3)]
    displacement = math.sqrt(sum(value * value for value in delta))
    direction = [value / displacement for value in delta] if displacement > 0.0 else [0.0, 0.0, 0.0]
    magnitudes = [math.sqrt(sum(component * component for component in sample)) for sample in translations]
    max_magnitude = max(magnitudes)
    worst_frame = magnitudes.index(max_magnitude)
    max_abs_component = max(abs(component) for sample in translations for component in sample)
    return {
        "unit": "mean-leg-length",
        "authority": "in-place-zero-translation",
        "start": start,
        "end": end,
        "delta": delta,
        "displacement": displacement,
        "direction": direction,
        "maxMagnitude": max_magnitude,
        "maxAbsComponent": max_abs_component,
        "worstFrame": worst_frame,
        "inPlaceTolerance": ROOT_TRANSLATION_TOLERANCE,
        "isInPlace": max_abs_component <= ROOT_TRANSLATION_TOLERANCE,
    }
