from __future__ import annotations

import math
from typing import Any


def contract_root_motion(rig: dict[str, Any], animation: dict[str, Any]) -> dict[str, Any]:
    """Measure root translation semantics directly from Contract B.

    No filename/action naming convention is consulted. The unique hierarchy root and
    the first/last Contract B samples are the only authorities used by this diagnostic.
    """

    roots = [bone["name"] for bone in rig["bones"] if bone.get("parent") is None]
    if len(roots) != 1:
        raise ValueError(f"Contract B rig must have exactly one root bone; found {roots}")
    frames = animation.get("frames") or []
    if not frames:
        raise ValueError("Contract B animation has no frames")
    root = roots[0]

    def translation(frame: dict[str, Any]) -> list[float]:
        bones = frame.get("bones") or {}
        if root not in bones:
            raise ValueError(f"Contract B frame {frame.get('frame')} is missing root bone {root!r}")
        values = bones[root].get("translation")
        if not isinstance(values, list) or len(values) != 3:
            raise ValueError(f"Contract B root translation must contain three components for {root!r}")
        result = [float(value) for value in values]
        if not all(math.isfinite(value) for value in result):
            raise ValueError(f"Contract B root translation contains non-finite values for {root!r}")
        return result

    start = translation(frames[0])
    end = translation(frames[-1])
    delta = [end[index] - start[index] for index in range(3)]
    displacement = math.sqrt(sum(value * value for value in delta))
    direction = [value / displacement for value in delta] if displacement > 0.0 else [0.0, 0.0, 0.0]
    return {
        "rootBone": root,
        "rootTranslationStart": start,
        "rootTranslationEnd": end,
        "rootTranslationDelta": delta,
        "rootDisplacement": displacement,
        "rootDirection": direction,
        "startFrame": int(frames[0]["frame"]),
        "endFrame": int(frames[-1]["frame"]),
        "frameCount": len(frames),
    }


def root_motion_difference(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    """Fail-closed data-driven proof that two Contract B clips keep distinct root motion."""

    first_displacement = float(first["rootDisplacement"])
    second_displacement = float(second["rootDisplacement"])
    scale = max(first_displacement, second_displacement, 1e-12)
    absolute_difference = abs(first_displacement - second_displacement)
    relative_difference = absolute_difference / scale
    return {
        "pass": absolute_difference > 1e-6 and relative_difference > 0.01,
        "absoluteDisplacementDifference": absolute_difference,
        "relativeDisplacementDifference": relative_difference,
        "largerMotion": "first" if first_displacement > second_displacement else "second" if second_displacement > first_displacement else "equal",
        "absoluteTolerance": 1e-6,
        "relativeTolerance": 0.01,
    }
