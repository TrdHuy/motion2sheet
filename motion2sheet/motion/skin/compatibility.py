from __future__ import annotations

import math
from typing import Any

from motion2sheet.motion.roundtrip.schema import validate_rig_document

REST_BASIS_TOLERANCE_DEGREES = 0.001


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _length(value):
    return math.sqrt(_dot(value, value))


def _unit(value):
    length = _length(value)
    if length <= 1e-12:
        raise ValueError("zero-length bone in rest rig")
    return tuple(component / length for component in value)


def _axis_angle(axis, angle):
    x, y, z = _unit(axis)
    c = math.cos(angle)
    s = math.sin(angle)
    t = 1.0 - c
    return (
        (t * x * x + c, t * x * y - s * z, t * x * z + s * y),
        (t * x * y + s * z, t * y * y + c, t * y * z - s * x),
        (t * x * z - s * y, t * y * z + s * x, t * z * z + c),
    )


def _mul3(first, second):
    return tuple(tuple(sum(first[row][k] * second[k][column] for k in range(3)) for column in range(3)) for row in range(3))


def _transpose3(matrix):
    return tuple(tuple(matrix[column][row] for column in range(3)) for row in range(3))


def _vec_roll_to_mat3(vector, roll):
    x, y, z = _unit(vector)
    theta = 1.0 + y
    theta_alt = x * x + z * z
    safe = 6.1e-3
    critical = 2.5e-4
    if theta > safe or theta_alt > critical * critical:
        if theta <= safe:
            theta = theta_alt * 0.5 + theta_alt * theta_alt * 0.125
        base = (
            (1.0 - x * x / theta, x, -x * z / theta),
            (-x, y, -z),
            (-x * z / theta, z, 1.0 - z * z / theta),
        )
    else:
        base = ((-1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, 1.0))
    return _mul3(_axis_angle((x, y, z), float(roll)), base)


def _rotation_error_degrees(first, second):
    delta = _mul3(_transpose3(first), second)
    cosine = max(-1.0, min(1.0, (delta[0][0] + delta[1][1] + delta[2][2] - 1.0) * 0.5))
    return math.degrees(math.acos(cosine))


def _rows(rig: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        bone["name"]: {
            "name": bone["name"],
            "parent": bone["parent"],
            "head": tuple(float(value) for value in bone["editGeometry"]["head"]),
            "tail": tuple(float(value) for value in bone["editGeometry"]["tail"]),
            "roll": float(bone["editGeometry"]["roll"]),
        }
        for bone in rig["bones"]
    }


def _local_bases(rows: dict[str, dict[str, Any]]):
    absolute = {
        name: _vec_roll_to_mat3(_sub(row["tail"], row["head"]), row["roll"])
        for name, row in rows.items()
    }
    return {
        name: absolute[name] if row["parent"] is None else _mul3(_transpose3(absolute[row["parent"]]), absolute[name])
        for name, row in rows.items()
    }


def validate_level1_rig_compatibility(
    animation_rig: dict[str, Any],
    character_rig: dict[str, Any],
    *,
    rest_basis_tolerance_degrees: float = REST_BASIS_TOLERANCE_DEGREES,
) -> dict[str, Any]:
    if rest_basis_tolerance_degrees < 0.0:
        raise ValueError("rest basis tolerance must be non-negative")
    source = validate_rig_document(animation_rig)
    target = validate_rig_document(character_rig)
    source_rows = _rows(source)
    target_rows = _rows(target)
    source_names = set(source_rows)
    target_names = set(target_rows)
    missing = sorted(source_names - target_names)
    extra = sorted(target_names - source_names)
    if missing or extra:
        raise ValueError(f"Level-1 bone set mismatch: missing={missing} extra={extra}")

    for name in sorted(source_names):
        source_parent = source_rows[name]["parent"]
        target_parent = target_rows[name]["parent"]
        if source_parent != target_parent:
            raise ValueError(
                f"Level-1 parent mismatch for {name}: animation={source_parent!r} character={target_parent!r}"
            )

    source_coordinate = source["coordinateSystem"]
    target_coordinate = target["coordinateSystem"]
    for field in ("handedness", "rightAxis", "forwardAxis", "upAxis"):
        if source_coordinate.get(field) != target_coordinate.get(field):
            raise ValueError(
                f"Level-1 coordinate convention mismatch for {field}: "
                f"animation={source_coordinate.get(field)!r} character={target_coordinate.get(field)!r}"
            )

    source_bases = _local_bases(source_rows)
    target_bases = _local_bases(target_rows)
    max_error = -1.0
    worst = None
    for name in sorted(source_names):
        error = _rotation_error_degrees(source_bases[name], target_bases[name])
        if error > max_error:
            max_error = error
            worst = name
        if error > rest_basis_tolerance_degrees:
            raise ValueError(
                f"Level-1 rest-basis mismatch for {name}: "
                f"error={error:.12g}deg tolerance={rest_basis_tolerance_degrees:.12g}deg"
            )

    return {
        "pass": True,
        "level": 1,
        "boneCount": len(source_names),
        "exactBoneNames": True,
        "exactHierarchy": True,
        "coordinateConventionMatch": True,
        "restBasisToleranceDegrees": rest_basis_tolerance_degrees,
        "maxRestBasisErrorDegrees": max_error,
        "worstRestBasisBone": worst,
        "retargeting": False,
        "fuzzyMapping": False,
    }
