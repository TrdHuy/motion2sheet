from __future__ import annotations

import math
from typing import Any, Iterable


LEGACY_POINTS: tuple[tuple[float, float, float], ...] = (
    (1.15, 1.06, 0.0),
    (.57, 1.03, 0.0),
    (.06, .83, 0.0),
    (-.25, .49, 0.0),
    (-.23, .10, 0.0),
    (.02, -.29, 0.0),
    (.47, -.54, 0.0),
    (1.18, -.61, 0.0),
)


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _catmull3(p0, p1, p2, p3, t: float) -> tuple[float, float, float]:
    t2 = t * t
    t3 = t2 * t
    values = []
    for axis in range(3):
        values.append(
            .5 * ((2 * p1[axis]) + (-p0[axis] + p2[axis]) * t +
                  (2 * p0[axis] - 5 * p1[axis] + 4 * p2[axis] - p3[axis]) * t2 +
                  (-p0[axis] + 3 * p1[axis] - 3 * p2[axis] + p3[axis]) * t3)
        )
    return values[0], values[1], values[2]


def _coerce_points(points: Iterable[Iterable[float]], dimensions: int) -> tuple[tuple[float, float, float], ...]:
    out = []
    for point in points:
        values = tuple(float(value) for value in point)
        if len(values) != dimensions:
            raise RuntimeError(f"Blender trajectory expected {dimensions}D points")
        if dimensions == 2:
            out.append((values[0], values[1], 0.0))
        else:
            out.append((values[0], values[1], values[2]))
    if len(out) < 2:
        raise RuntimeError("Blender trajectory requires at least 2 points")
    return tuple(out)


def _sample_control_points(points: tuple[tuple[float, float, float], ...], t: float) -> tuple[float, float, float]:
    t = clamp01(t)
    n = len(points) - 1
    scaled = t * n
    segment = min(n - 1, int(scaled))
    q = scaled - segment
    p1, p2 = points[segment], points[segment + 1]
    p0 = points[segment - 1] if segment > 0 else p1
    p3 = points[segment + 2] if segment + 2 < len(points) else p2
    return _catmull3(p0, p1, p2, p3, q)


def _generated_conical_helix(config: dict[str, Any]) -> tuple[tuple[float, float, float], ...]:
    samples = int(config["samples"])
    turns = float(config["turns"])
    bottom = float(config["bottom"])
    top = float(config["top"])
    radius_start = float(config["radiusStart"])
    radius_end = float(config["radiusEnd"])
    phase = math.radians(float(config.get("phaseDegrees", 0.0)))
    points = []
    for index in range(samples):
        t = index / max(1, samples - 1)
        radius = radius_start + (radius_end - radius_start) * t
        angle = phase + turns * math.tau * t
        points.append((
            radius * math.cos(angle),
            bottom + (top - bottom) * t,
            radius * math.sin(angle),
        ))
    return tuple(points)


def _normalize3(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(sum(value * value for value in vector))
    if length <= 1e-12:
        return 1.0, 0.0, 0.0
    return tuple(value / length for value in vector)  # type: ignore[return-value]


def _cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


class BlenderTrajectory3D:
    """Blender-side 2D/3D trajectory with deterministic projected compatibility."""

    def __init__(self, config: dict[str, Any] | None):
        self.config = config
        self.scale_start = 1.0
        self.scale_end = 1.0
        self._projection_cache: dict[tuple[float, ...], tuple[tuple[float, float, float, float], ...]] = {}
        if config is None:
            self.kind = "legacy"
            self.dimensions = 2
            self.points = LEGACY_POINTS
        else:
            self.kind = str(config.get("type", "points")).lower()
            interpolation = str(config.get("interpolation", "catmull-rom")).lower()
            if interpolation != "catmull-rom":
                raise RuntimeError(f"Unsupported Blender trajectory interpolation: {interpolation}")
            if bool(config.get("closed", False)):
                raise RuntimeError("Closed Blender trajectories are not supported yet")
            scale = config.get("scale") or {}
            self.scale_start = float(scale.get("start", 1.0))
            self.scale_end = float(scale.get("end", 1.0))
            if self.kind == "points":
                raw_points = config.get("points", ())
                dimensions = int(config.get("dimensions", len(raw_points[0]) if raw_points else 2))
                if dimensions not in (2, 3):
                    raise RuntimeError("Blender point trajectory dimensions must be 2 or 3")
                self.dimensions = dimensions
                self.points = _coerce_points(raw_points, dimensions)
            elif self.kind == "conical-helix":
                self.dimensions = 3
                self.points = _generated_conical_helix(config)
            else:
                raise RuntimeError(f"Unsupported Blender trajectory type: {self.kind}")

    @property
    def has_depth(self) -> bool:
        return self.dimensions == 3 and any(abs(point[2]) > 1e-12 for point in self.points)

    @property
    def has_variable_scale(self) -> bool:
        return abs(self.scale_start - 1.0) > 1e-12 or abs(self.scale_end - 1.0) > 1e-12

    @property
    def needs_geometry_warp(self) -> bool:
        return self.has_depth or self.has_variable_scale

    def scale_at(self, t: float) -> float:
        t = clamp01(t)
        return self.scale_start + (self.scale_end - self.scale_start) * t

    def raw_position3d(self, radius: float, t: float, params: dict[str, Any]) -> tuple[float, float, float]:
        t = clamp01(t)
        x, y, z = _sample_control_points(self.points, t)
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
        z *= radius
        x += float(params["shape.offset_x"]) * radius * 3.0
        y -= float(params["shape.offset_y"]) * radius * 3.0
        return x, y, z

    def raw_position(self, radius: float, t: float, params: dict[str, Any]) -> tuple[float, float]:
        x, y, _z = self.raw_position3d(radius, t, params)
        return x, y

    def sample_projected(self, radius: float, t: float, params: dict[str, Any]) -> tuple[float, float, float, float, float, float, float]:
        t = clamp01(t)
        x, y, _z = self.raw_position3d(radius, t, params)
        epsilon = .0015
        xa, ya, _za = self.raw_position3d(radius, max(0.0, t - epsilon), params)
        xb, yb, _zb = self.raw_position3d(radius, min(1.0, t + epsilon), params)
        dx, dy = xb - xa, yb - ya
        length = math.hypot(dx, dy)
        if length <= 1e-12:
            dx, dy, length = 1.0, 0.0, 1.0
        tx, ty = dx / length, dy / length
        nx, ny = ty, -tx
        return x, y, tx, ty, nx, ny, self.scale_at(t)

    def sample3d(self, radius: float, t: float, params: dict[str, Any]) -> tuple[float, ...]:
        t = clamp01(t)
        x, y, z = self.raw_position3d(radius, t, params)
        epsilon = .0015
        a = self.raw_position3d(radius, max(0.0, t - epsilon), params)
        b = self.raw_position3d(radius, min(1.0, t + epsilon), params)
        tangent = _normalize3((b[0] - a[0], b[1] - a[1], b[2] - a[2]))
        reference = (0.0, 0.0, 1.0)
        if abs(tangent[2]) > .94:
            reference = (0.0, 1.0, 0.0)
        normal = _normalize3(_cross(reference, tangent))
        binormal = _normalize3(_cross(tangent, normal))
        return (x, y, z, *tangent, *normal, *binormal, self.scale_at(t))

    def point_on_spine(self, radius: float, t: float, params: dict[str, Any]) -> tuple[float, float, float]:
        x, y, _tx, _ty, nx, ny, _scale = self.sample_projected(radius, t, params)
        return x, y, math.atan2(ny, nx)

    def _cache_key(self, radius: float, params: dict[str, Any]) -> tuple[float, ...]:
        return (
            float(radius),
            float(params["shape.form_noise"]),
            float(params["shape.form_noise_frequency"]),
            float(params.get("rotation", 0.0)),
            float(params["shape.offset_x"]),
            float(params["shape.offset_y"]),
        )

    def _projection_table(self, radius: float, params: dict[str, Any]) -> tuple[tuple[float, float, float, float], ...]:
        key = self._cache_key(radius, params)
        cached = self._projection_cache.get(key)
        if cached is not None:
            return cached
        samples = 161
        table = []
        for index in range(samples):
            t = index / (samples - 1)
            x, y, z = self.raw_position3d(radius, t, params)
            table.append((t, x, y, z))
        result = tuple(table)
        self._projection_cache[key] = result
        return result

    def closest_projected(self, x: float, y: float, radius: float, params: dict[str, Any]) -> tuple[float, float, float, float, float]:
        table = self._projection_table(radius, params)
        best = min(table, key=lambda item: (x - item[1]) ** 2 + (y - item[2]) ** 2)
        return best[0], best[1], best[2], best[3], self.scale_at(best[0])


class BlenderTrajectory(BlenderTrajectory3D):
    """Compatibility facade for the original 2D trajectory API."""

    def sample(self, radius: float, t: float, params: dict[str, Any]) -> tuple[float, float, float, float, float, float]:
        return self.sample_projected(radius, t, params)[:6]
