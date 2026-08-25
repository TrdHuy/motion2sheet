from __future__ import annotations

import math
from typing import Any, Iterable


LEGACY_POINTS: tuple[tuple[float, float], ...] = (
    (1.15, 1.06),
    (.57, 1.03),
    (.06, .83),
    (-.25, .49),
    (-.23, .10),
    (.02, -.29),
    (.47, -.54),
    (1.18, -.61),
)


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _catmull(p0, p1, p2, p3, t: float) -> tuple[float, float]:
    t2 = t * t
    t3 = t2 * t
    return (
        .5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t +
              (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
              (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
        .5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t +
              (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
              (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3),
    )


def _coerce_points(points: Iterable[Iterable[float]]) -> tuple[tuple[float, float], ...]:
    out = tuple((float(point[0]), float(point[1])) for point in points)
    if len(out) < 2:
        raise RuntimeError("Blender trajectory requires at least 2 points")
    return out


def _sample_control_points(points: tuple[tuple[float, float], ...], t: float) -> tuple[float, float]:
    t = clamp01(t)
    n = len(points) - 1
    scaled = t * n
    segment = min(n - 1, int(scaled))
    q = scaled - segment
    p1, p2 = points[segment], points[segment + 1]
    p0 = points[segment - 1] if segment > 0 else p1
    p3 = points[segment + 2] if segment + 2 < len(points) else p2
    return _catmull(p0, p1, p2, p3, q)


class BlenderTrajectory:
    """Deterministic trajectory provider used directly by Blender geometry code.

    Input points are local VFX coordinates. Existing form noise, rotation, radius
    scaling and shape offsets are applied here so every downstream VFX layer sees
    one canonical position/tangent/normal field.
    """

    def __init__(self, config: dict[str, Any] | None):
        if config is None:
            self.kind = "legacy"
            self.points = LEGACY_POINTS
        else:
            kind = str(config.get("type", "points")).lower()
            interpolation = str(config.get("interpolation", "catmull-rom")).lower()
            if kind != "points":
                raise RuntimeError(f"Unsupported Blender trajectory type: {kind}")
            if interpolation != "catmull-rom":
                raise RuntimeError(f"Unsupported Blender trajectory interpolation: {interpolation}")
            if bool(config.get("closed", False)):
                raise RuntimeError("Closed Blender trajectories are not supported yet")
            self.kind = "points"
            self.points = _coerce_points(config.get("points", ()))

    def raw_position(self, radius: float, t: float, params: dict[str, Any]) -> tuple[float, float]:
        x, y = _sample_control_points(self.points, t)

        # Preserve V16's exact low-frequency shape warp and transform order.
        form = float(params["shape.form_noise"])
        frequency = float(params["shape.form_noise_frequency"])
        x += form * (.042 * math.sin(math.tau * .43 * frequency * t + .22) +
                     .016 * math.sin(math.tau * .79 * frequency * t + 1.10))
        y += form * (.030 * math.sin(math.tau * .37 * frequency * t + .91) +
                     .012 * math.sin(math.tau * .73 * frequency * t + .35))

        rotation = math.radians(float(params.get("rotation", 0.0)))
        cosine, sine = math.cos(rotation), math.sin(rotation)
        x, y = x * cosine - y * sine, x * sine + y * cosine
        x *= radius
        y *= radius
        x += float(params["shape.offset_x"]) * radius * 3.0
        y -= float(params["shape.offset_y"]) * radius * 3.0
        return x, y

    def sample(self, radius: float, t: float, params: dict[str, Any]) -> tuple[float, float, float, float, float, float]:
        t = clamp01(t)
        x, y = self.raw_position(radius, t, params)
        epsilon = .0015
        xa, ya = self.raw_position(radius, max(0.0, t - epsilon), params)
        xb, yb = self.raw_position(radius, min(1.0, t + epsilon), params)
        dx, dy = xb - xa, yb - ya
        length = math.hypot(dx, dy)
        if length <= 1e-12:
            # Deterministic fallback for an extremely local tangent degeneracy.
            dx, dy, length = 1.0, 0.0, 1.0
        tx, ty = dx / length, dy / length
        nx, ny = ty, -tx
        return x, y, tx, ty, nx, ny

    def point_on_spine(self, radius: float, t: float, params: dict[str, Any]) -> tuple[float, float, float]:
        x, y, _tx, _ty, nx, ny = self.sample(radius, t, params)
        return x, y, math.atan2(ny, nx)
