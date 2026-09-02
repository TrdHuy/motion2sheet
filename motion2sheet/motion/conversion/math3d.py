from __future__ import annotations

import math
from typing import Sequence

Vec3 = tuple[float, float, float]
Mat3 = tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]
Mat4 = tuple[
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
]

EPS = 1e-12


def vec3(values: Sequence[float]) -> Vec3:
    if len(values) != 3:
        raise ValueError(f"expected vec3, got {values!r}")
    return float(values[0]), float(values[1]), float(values[2])


def add(a: Vec3, b: Vec3) -> Vec3:
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def sub(a: Vec3, b: Vec3) -> Vec3:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def mul(v: Vec3, scalar: float) -> Vec3:
    return v[0] * scalar, v[1] * scalar, v[2] * scalar


def dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def length(v: Vec3) -> float:
    return math.sqrt(dot(v, v))


def distance(a: Vec3, b: Vec3) -> float:
    return length(sub(a, b))


def unit(v: Vec3, label: str = "vector") -> Vec3:
    value = length(v)
    if not math.isfinite(value) or value <= EPS:
        raise ValueError(f"{label} has no stable direction")
    return mul(v, 1.0 / value)


def clean(value: float, digits: int = 9) -> float:
    value = round(float(value), digits)
    return 0.0 if value == 0.0 else value


def clean_vec(v: Vec3, digits: int = 9) -> list[float]:
    return [clean(value, digits) for value in v]


def identity3() -> Mat3:
    return ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def transpose3(m: Mat3) -> Mat3:
    return tuple(tuple(m[c][r] for c in range(3)) for r in range(3))  # type: ignore[return-value]


def mul3(a: Mat3, b: Mat3) -> Mat3:
    return tuple(
        tuple(sum(a[r][k] * b[k][c] for k in range(3)) for c in range(3))
        for r in range(3)
    )  # type: ignore[return-value]


def mul3v(m: Mat3, v: Vec3) -> Vec3:
    return tuple(sum(m[r][c] * v[c] for c in range(3)) for r in range(3))  # type: ignore[return-value]


def det3(m: Mat3) -> float:
    return (
        m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
        - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
        + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
    )


def inverse3(m: Mat3) -> Mat3:
    d = det3(m)
    if abs(d) <= EPS:
        raise ValueError("matrix is singular")
    inv = (
        (
            m[1][1] * m[2][2] - m[1][2] * m[2][1],
            m[0][2] * m[2][1] - m[0][1] * m[2][2],
            m[0][1] * m[1][2] - m[0][2] * m[1][1],
        ),
        (
            m[1][2] * m[2][0] - m[1][0] * m[2][2],
            m[0][0] * m[2][2] - m[0][2] * m[2][0],
            m[0][2] * m[1][0] - m[0][0] * m[1][2],
        ),
        (
            m[1][0] * m[2][1] - m[1][1] * m[2][0],
            m[0][1] * m[2][0] - m[0][0] * m[2][1],
            m[0][0] * m[1][1] - m[0][1] * m[1][0],
        ),
    )
    return tuple(tuple(value / d for value in row) for row in inv)  # type: ignore[return-value]


def orthonormalize(m: Mat3) -> Mat3:
    x = unit((m[0][0], m[1][0], m[2][0]), "matrix X axis")
    y_raw = (m[0][1], m[1][1], m[2][1])
    y = unit(sub(y_raw, mul(x, dot(y_raw, x))), "matrix Y axis")
    z = unit(cross(x, y), "matrix Z axis")
    if dot(z, (m[0][2], m[1][2], m[2][2])) < 0.0:
        z = mul(z, -1.0)
        y = mul(y, -1.0)
    return (
        (x[0], y[0], z[0]),
        (x[1], y[1], z[1]),
        (x[2], y[2], z[2]),
    )


def axis_rotation(axis: Vec3, angle: float) -> Mat3:
    x, y, z = unit(axis, "rotation axis")
    c, s, t = math.cos(angle), math.sin(angle), 1.0 - math.cos(angle)
    return (
        (t * x * x + c, t * x * y - s * z, t * x * z + s * y),
        (t * x * y + s * z, t * y * y + c, t * y * z - s * x),
        (t * x * z - s * y, t * y * z + s * x, t * z * z + c),
    )


def axis_named_rotation(axis: str, angle: float) -> Mat3:
    axes = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}
    try:
        return axis_rotation(axes[axis.upper()], angle)
    except KeyError as exc:
        raise ValueError(f"unsupported rotation axis {axis!r}") from exc


def euler_xyz_matrix(x: float, y: float, z: float) -> Mat3:
    return mul3(axis_named_rotation("Z", z), mul3(axis_named_rotation("Y", y), axis_named_rotation("X", x)))


def euler_xyz_from_matrix(matrix: Mat3) -> tuple[float, float, float]:
    m = orthonormalize(matrix)
    sy = max(-1.0, min(1.0, -m[2][0]))
    y = math.asin(sy)
    cy = math.cos(y)
    if abs(cy) > 1e-8:
        x = math.atan2(m[2][1], m[2][2])
        z = math.atan2(m[1][0], m[0][0])
    else:
        x = math.atan2(-m[1][2], m[1][1])
        z = 0.0
    return x, y, z


def quat_matrix(values: Sequence[float]) -> Mat3:
    if len(values) != 4:
        raise ValueError("quaternion must contain four values")
    w, x, y, z = [float(v) for v in values]
    n = math.sqrt(w * w + x * x + y * y + z * z)
    if n <= EPS:
        raise ValueError("quaternion is zero")
    w, x, y, z = [v / n for v in (w, x, y, z)]
    return (
        (1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)),
        (2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)),
        (2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)),
    )


def quat_from_matrix(matrix: Mat3) -> list[float]:
    m = orthonormalize(matrix)
    trace = m[0][0] + m[1][1] + m[2][2]
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        w, x, y, z = 0.25 * s, (m[2][1] - m[1][2]) / s, (m[0][2] - m[2][0]) / s, (m[1][0] - m[0][1]) / s
    elif m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2]) * 2.0
        w, x, y, z = (m[2][1] - m[1][2]) / s, 0.25 * s, (m[0][1] + m[1][0]) / s, (m[0][2] + m[2][0]) / s
    elif m[1][1] > m[2][2]:
        s = math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2]) * 2.0
        w, x, y, z = (m[0][2] - m[2][0]) / s, (m[0][1] + m[1][0]) / s, 0.25 * s, (m[1][2] + m[2][1]) / s
    else:
        s = math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1]) * 2.0
        w, x, y, z = (m[1][0] - m[0][1]) / s, (m[0][2] + m[2][0]) / s, (m[1][2] + m[2][1]) / s, 0.25 * s
    q = [w, x, y, z]
    n = math.sqrt(sum(v * v for v in q))
    q = [v / n for v in q]
    if q[0] < 0:
        q = [-v for v in q]
    return [clean(v, 12) for v in q]


def vec_roll_to_mat3(vector: Vec3, roll: float) -> Mat3:
    v = unit(vector, "bone vector")
    x, y, z = v
    theta = 1.0 + y
    theta_alt = x * x + z * z
    safe_threshold = 6.1e-3
    critical_threshold = 2.5e-4
    if theta > safe_threshold or theta_alt > critical_threshold * critical_threshold:
        if theta <= safe_threshold:
            theta = theta_alt * 0.5 + theta_alt * theta_alt * 0.125
        base: Mat3 = (
            (1.0 - x * x / theta, x, -x * z / theta),
            (-x, y, -z),
            (-x * z / theta, z, 1.0 - z * z / theta),
        )
    else:
        base = ((-1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, 1.0))
    return mul3(axis_rotation(v, float(roll)), base)


def rest_matrix(head: Sequence[float], tail: Sequence[float], roll: float = 0.0) -> Mat4:
    h, t = vec3(head), vec3(tail)
    return from_rotation_translation(vec_roll_to_mat3(sub(t, h), float(roll)), h)


def from_rotation_translation(rotation: Mat3, translation: Vec3) -> Mat4:
    return (
        (rotation[0][0], rotation[0][1], rotation[0][2], translation[0]),
        (rotation[1][0], rotation[1][1], rotation[1][2], translation[1]),
        (rotation[2][0], rotation[2][1], rotation[2][2], translation[2]),
        (0.0, 0.0, 0.0, 1.0),
    )


def from_trs(translation: Sequence[float], quaternion: Sequence[float], scale: Sequence[float]) -> Mat4:
    r = quat_matrix(quaternion)
    s = vec3(scale)
    linear: Mat3 = tuple(
        tuple(r[row][column] * s[column] for column in range(3))
        for row in range(3)
    )  # type: ignore[assignment]
    return (
        (linear[0][0], linear[0][1], linear[0][2], float(translation[0])),
        (linear[1][0], linear[1][1], linear[1][2], float(translation[1])),
        (linear[2][0], linear[2][1], linear[2][2], float(translation[2])),
        (0.0, 0.0, 0.0, 1.0),
    )


def mul4(a: Mat4, b: Mat4) -> Mat4:
    return tuple(
        tuple(sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4))
        for r in range(4)
    )  # type: ignore[return-value]


def linear4(m: Mat4) -> Mat3:
    return tuple(tuple(m[r][c] for c in range(3)) for r in range(3))  # type: ignore[return-value]


def rotation4(m: Mat4) -> Mat3:
    return orthonormalize(linear4(m))


def translation4(m: Mat4) -> Vec3:
    return m[0][3], m[1][3], m[2][3]


def inverse_affine(m: Mat4) -> Mat4:
    linear = linear4(m)
    inv = inverse3(linear)
    t = translation4(m)
    inv_t = mul3v(inv, (-t[0], -t[1], -t[2]))
    return from_rotation_translation(inv, inv_t)


def point(m: Mat4, v: Vec3 = (0.0, 0.0, 0.0)) -> Vec3:
    return (
        m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2] + m[0][3],
        m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2] + m[1][3],
        m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2] + m[2][3],
    )


def with_rotation(base: Mat4, rotation: Mat3) -> Mat4:
    return from_rotation_translation(rotation, translation4(base))


def rotate_around_axis(vector: Vec3, axis: Vec3, angle: float) -> Vec3:
    return mul3v(axis_rotation(axis, angle), vector)
