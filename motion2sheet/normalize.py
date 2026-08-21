from __future__ import annotations

import math
from typing import Dict, Tuple

from .model import PoseFrame, PoseSequence

RawFrame = Dict[str, Tuple[float, float]]


def _ground_anchor(frame: RawFrame) -> tuple[float, float]:
    if "pelvis" in frame:
        anchor_x = frame["pelvis"][0]
    else:
        anchor_x = sum(x for x, _ in frame.values()) / max(len(frame), 1)

    ankle_points = [frame[name] for name in ("left_ankle", "right_ankle") if name in frame]
    if ankle_points:
        ground_y = min(y for _, y in ankle_points)
    else:
        ground_y = min(y for _, y in frame.values())
    return anchor_x, ground_y


def normalize_projected_sequences(
    raw_sequences: dict[str, list[RawFrame]],
    *,
    action: str,
    canvas: tuple[int, int] = (320, 320),
    anchor: tuple[float, float] | None = None,
    padding: int = 20,
) -> dict[str, PoseSequence]:
    """Normalize all directions with one global scale.

    Input y coordinates increase upward. Output raster y increases downward.
    """
    if not raw_sequences:
        raise ValueError("No pose sequences supplied")

    width, height = canvas
    target_anchor = anchor or (width / 2.0, height * 0.84)

    relative_frames: dict[str, list[RawFrame]] = {}
    min_dx = math.inf
    max_dx = -math.inf
    min_dy = math.inf
    max_dy = -math.inf

    for direction, frames in raw_sequences.items():
        if not frames:
            raise ValueError(f"Direction {direction!r} has no frames")
        relative_frames[direction] = []
        for frame in frames:
            if not frame:
                raise ValueError(f"Direction {direction!r} contains an empty frame")
            ax, ay = _ground_anchor(frame)
            rel: RawFrame = {}
            for joint, (x, y) in frame.items():
                dx, dy = x - ax, y - ay
                rel[joint] = (dx, dy)
                min_dx = min(min_dx, dx)
                max_dx = max(max_dx, dx)
                min_dy = min(min_dy, dy)
                max_dy = max(max_dy, dy)
            relative_frames[direction].append(rel)

    if not all(math.isfinite(v) for v in (min_dx, max_dx, min_dy, max_dy)):
        raise ValueError("Pose extents are not finite")

    left_room = target_anchor[0] - padding
    right_room = width - target_anchor[0] - padding
    above_room = target_anchor[1] - padding
    below_room = height - target_anchor[1] - padding

    scale_limits: list[float] = []
    if min_dx < 0:
        scale_limits.append(left_room / abs(min_dx))
    if max_dx > 0:
        scale_limits.append(right_room / max_dx)
    if max_dy > 0:
        scale_limits.append(above_room / max_dy)
    if min_dy < 0:
        scale_limits.append(below_room / abs(min_dy))

    global_scale = min(scale_limits) if scale_limits else 1.0
    if not math.isfinite(global_scale) or global_scale <= 0:
        raise ValueError("Unable to compute a valid global scale")

    result: dict[str, PoseSequence] = {}
    for direction, frames in relative_frames.items():
        normalized_frames: list[PoseFrame] = []
        for frame in frames:
            joints = {
                joint: (
                    target_anchor[0] + dx * global_scale,
                    target_anchor[1] - dy * global_scale,
                )
                for joint, (dx, dy) in frame.items()
            }
            normalized_frames.append(PoseFrame(joints))
        result[direction] = PoseSequence(
            action=action,
            direction=direction,
            canvas=canvas,
            anchor=target_anchor,
            frames=normalized_frames,
        )
    return result
