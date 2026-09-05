from __future__ import annotations

import math
from typing import Any

from motion2sheet.motion.roundtrip.schema import validate_rig_document

REST_BASIS_TOLERANCE_DEGREES = 0.001
_COORDINATE_FIELDS = ("handedness", "rightAxis", "forwardAxis", "upAxis")


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


def diagnose_level1_rig_compatibility(
    animation_rig: dict[str, Any],
    character_rig: dict[str, Any],
    *,
    rest_basis_tolerance_degrees: float = REST_BASIS_TOLERANCE_DEGREES,
) -> dict[str, Any]:
    """Return a complete, deterministic Level-1 compatibility report.

    This function is diagnostic only: it never performs retargeting, fuzzy mapping,
    or tolerance adaptation. Structural and coordinate mismatches are collected so
    CI can explain an incompatible fixture in one artifact instead of stopping at
    the first bone. The strict validator below preserves fail-closed behavior.
    """
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
    common_names = sorted(source_names & target_names)

    parent_mismatches = []
    for name in common_names:
        source_parent = source_rows[name]["parent"]
        target_parent = target_rows[name]["parent"]
        if source_parent != target_parent:
            parent_mismatches.append(
                {
                    "bone": name,
                    "animationParent": source_parent,
                    "characterParent": target_parent,
                }
            )

    source_coordinate = source["coordinateSystem"]
    target_coordinate = target["coordinateSystem"]
    coordinate_mismatches = []
    for field in _COORDINATE_FIELDS:
        source_value = source_coordinate.get(field)
        target_value = target_coordinate.get(field)
        if source_value != target_value:
            coordinate_mismatches.append(
                {
                    "field": field,
                    "animation": source_value,
                    "character": target_value,
                }
            )

    rest_errors: list[dict[str, Any]] = []
    max_error: float | None = None
    worst: str | None = None
    if not missing and not extra and not parent_mismatches:
        source_bases = _local_bases(source_rows)
        target_bases = _local_bases(target_rows)
        max_error = -1.0
        for name in sorted(source_names):
            error = _rotation_error_degrees(source_bases[name], target_bases[name])
            if error > max_error:
                max_error = error
                worst = name
            if error > rest_basis_tolerance_degrees:
                rest_errors.append({"bone": name, "errorDegrees": error})

    exact_bones = not missing and not extra
    exact_hierarchy = exact_bones and not parent_mismatches
    coordinate_match = not coordinate_mismatches
    passed = exact_bones and exact_hierarchy and coordinate_match and not rest_errors

    return {
        "pass": passed,
        "level": 1,
        "boneCount": len(source_names),
        "exactBoneNames": exact_bones,
        "exactHierarchy": exact_hierarchy,
        "coordinateConventionMatch": coordinate_match,
        "missingBones": missing,
        "extraBones": extra,
        "parentMismatches": parent_mismatches,
        "coordinateMismatches": coordinate_mismatches,
        "restBasisToleranceDegrees": rest_basis_tolerance_degrees,
        "maxRestBasisErrorDegrees": max_error,
        "worstRestBasisBone": worst,
        "restBasisMismatchCount": len(rest_errors),
        "restBasisMismatches": rest_errors,
        "retargeting": False,
        "fuzzyMapping": False,
    }


def validate_level1_rig_compatibility(
    animation_rig: dict[str, Any],
    character_rig: dict[str, Any],
    *,
    rest_basis_tolerance_degrees: float = REST_BASIS_TOLERANCE_DEGREES,
) -> dict[str, Any]:
    report = diagnose_level1_rig_compatibility(
        animation_rig,
        character_rig,
        rest_basis_tolerance_degrees=rest_basis_tolerance_degrees,
    )

    missing = report["missingBones"]
    extra = report["extraBones"]
    if missing or extra:
        raise ValueError(f"Level-1 bone set mismatch: missing={missing} extra={extra}")

    if report["parentMismatches"]:
        mismatch = report["parentMismatches"][0]
        raise ValueError(
            f"Level-1 parent mismatch for {mismatch['bone']}: "
            f"animation={mismatch['animationParent']!r} character={mismatch['characterParent']!r}"
        )

    if report["coordinateMismatches"]:
        mismatch = report["coordinateMismatches"][0]
        raise ValueError(
            f"Level-1 coordinate convention mismatch for {mismatch['field']}: "
            f"animation={mismatch['animation']!r} character={mismatch['character']!r}"
        )

    if report["restBasisMismatches"]:
        mismatch = report["restBasisMismatches"][0]
        raise ValueError(
            f"Level-1 rest-basis mismatch for {mismatch['bone']}: "
            f"error={mismatch['errorDegrees']:.12g}deg tolerance={rest_basis_tolerance_degrees:.12g}deg"
        )

    return report
