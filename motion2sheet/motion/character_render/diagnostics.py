from __future__ import annotations

from collections.abc import Iterable


def frame_bounds(frames: Iterable[int]) -> tuple[int, int]:
    values = [int(frame) for frame in frames]
    if not values:
        raise ValueError("diagnostics requires at least one animation frame")
    return min(values), max(values)
