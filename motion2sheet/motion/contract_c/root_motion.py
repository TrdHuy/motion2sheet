from __future__ import annotations

import math
from typing import Any


def contract_root_motion(animation: dict[str, Any]) -> dict[str, Any]:
    translations = animation["root"]["translations"]
    start = [float(value) for value in translations[0]]
    end = [float(value) for value in translations[-1]]
    delta = [end[index] - start[index] for index in range(3)]
    displacement = math.sqrt(sum(value * value for value in delta))
    direction = [value / displacement for value in delta] if displacement > 0.0 else [0.0, 0.0, 0.0]
    return {
        "unit": "mean-leg-length",
        "start": start,
        "end": end,
        "delta": delta,
        "displacement": displacement,
        "direction": direction,
        "inPlaceTolerance": 1e-4,
        "isInPlace": displacement <= 1e-4,
    }
