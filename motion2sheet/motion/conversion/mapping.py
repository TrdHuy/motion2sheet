from __future__ import annotations

import math
from pathlib import Path

import json5

from motion2sheet.anim2sheet.common.profile import load_rig_profile
from .math3d import Mat3, det3

MAPPING_SCHEMA = "motion2sheet.retarget-mapping"
MAPPING_VERSION = 1


def _object(value, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _string(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _matrix3(value, label: str) -> Mat3:
    if (
        not isinstance(value, list)
        or len(value) != 3
        or any(not isinstance(row, list) or len(row) != 3 for row in value)
    ):
        raise ValueError(f"{label} must be a 3x3 numeric matrix")
    rows = []
    for r, row in enumerate(value):
        values = []
        for c, item in enumerate(row):
            if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(float(item)):
                raise ValueError(f"{label}[{r}][{c}] must be finite numeric")
            values.append(float(item))
        rows.append(tuple(values))
    matrix: Mat3 = tuple(rows)  # type: ignore[assignment]
    for r in range(3):
        norm = math.sqrt(sum(matrix[r][c] ** 2 for c in range(3)))
        if abs(norm - 1.0) > 1e-8:
            raise ValueError(f"{label} row {r} must have unit length")
    for a in range(3):
        for b in range(a + 1, 3):
            dot = sum(matrix[a][c] * matrix[b][c] for c in range(3))
            if abs(dot) > 1e-8:
                raise ValueError(f"{label} rows {a}/{b} must be orthogonal")
    if abs(det3(matrix) - 1.0) > 1e-8:
        raise ValueError(f"{label} must be right-handed with determinant +1")
    return matrix


def load_mapping(path: Path, *, target_rig: dict | None = None) -> dict:
    path = path.resolve()
    try:
        data = json5.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"unable to read retarget mapping {path}: {exc}") from exc
    data = _object(data, "retarget mapping")
    allowed = {
        "schema", "version", "id", "targetRig", "sourceCoordinateSystem",
        "targetCoordinateSystem", "sourceToTargetAxes", "rootSourceBone",
        "requiredTargets", "bones", "poseErrorToleranceMeters",
    }
    unknown = set(data) - allowed
    required = allowed
    if unknown or required - set(data):
        raise ValueError(
            f"retarget mapping fields invalid: missing={sorted(required-set(data))} unknown={sorted(unknown)}"
        )
    if data["schema"] != MAPPING_SCHEMA or data["version"] != MAPPING_VERSION:
        raise ValueError(
            f"unsupported retarget mapping schema/version: {data['schema']!r}/{data['version']!r}"
        )
    mapping_id = _string(data["id"], "retarget mapping id")
    target = _object(data["targetRig"], "retarget mapping targetRig")
    if set(target) != {"schema", "version", "id"}:
        raise ValueError("retarget mapping targetRig must contain schema/version/id exactly")
    if target["schema"] != "anim2sheet.rig" or target["version"] != 2:
        raise ValueError("retarget mapping currently supports Anim2Sheet rig contract v2 only")
    _string(target["id"], "retarget mapping targetRig.id")

    source_coords = _object(data["sourceCoordinateSystem"], "retarget mapping sourceCoordinateSystem")
    expected_source = {
        "space": "Blender scene after source import",
        "handedness": "right-handed",
        "rightAxis": "+X",
        "forwardAxis": "-Y",
        "upAxis": "+Z",
    }
    if source_coords != expected_source:
        raise ValueError(
            f"retarget mapping sourceCoordinateSystem must match Contract B coordinates: {expected_source}"
        )

    target_coords = _object(data["targetCoordinateSystem"], "retarget mapping targetCoordinateSystem")
    expected_target = {
        "space": "world",
        "x": "screen-right",
        "y": "depth; negative is toward camera",
        "z": "up",
        "units": "Blender meters",
    }
    if target_coords != expected_target:
        raise ValueError(
            f"retarget mapping targetCoordinateSystem must match GameHumanoidV2 coordinates: {expected_target}"
        )
    axes = _matrix3(data["sourceToTargetAxes"], "retarget mapping sourceToTargetAxes")
    root_source_bone = _string(data["rootSourceBone"], "retarget mapping rootSourceBone")
    required_targets = data["requiredTargets"]
    if not isinstance(required_targets, list) or not required_targets:
        raise ValueError("retarget mapping requiredTargets must be a non-empty array")
    required_targets = [_string(value, "retarget mapping requiredTargets[]") for value in required_targets]
    if len(required_targets) != len(set(required_targets)):
        raise ValueError("retarget mapping requiredTargets contains duplicates")

    rows = data["bones"]
    if not isinstance(rows, list) or not rows:
        raise ValueError("retarget mapping bones must be a non-empty array")
    target_to_source: dict[str, str] = {}
    source_to_target: dict[str, str] = {}
    for index, raw in enumerate(rows):
        row = _object(raw, f"retarget mapping bones[{index}]")
        if set(row) != {"source", "target"}:
            raise ValueError(f"retarget mapping bones[{index}] must contain source/target exactly")
        source = _string(row["source"], f"retarget mapping bones[{index}].source")
        target_name = _string(row["target"], f"retarget mapping bones[{index}].target")
        if target_name in target_to_source:
            raise ValueError(f"ambiguous target mapping for {target_name!r}")
        if source in source_to_target:
            raise ValueError(
                f"source bone {source!r} maps to multiple target bones; mapping must be explicit one-to-one"
            )
        target_to_source[target_name] = source
        source_to_target[source] = target_name
    missing_required = set(required_targets) - set(target_to_source)
    if missing_required:
        raise ValueError(f"required target mappings missing: {sorted(missing_required)}")
    if root_source_bone not in source_to_target:
        raise ValueError("rootSourceBone must also appear in bones mapping")
    tolerance = data["poseErrorToleranceMeters"]
    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)):
        raise ValueError("poseErrorToleranceMeters must be numeric")
    tolerance = float(tolerance)
    if not math.isfinite(tolerance) or tolerance <= 0.0 or tolerance > 0.25:
        raise ValueError("poseErrorToleranceMeters must be finite and in (0, 0.25]")

    if target_rig is not None:
        if target["id"] != target_rig.get("id"):
            raise ValueError(
                f"mapping target rig mismatch: mapping={target['id']!r} actual={target_rig.get('id')!r}"
            )
        actual_coords = target_rig.get("coordinateSystem")
        if actual_coords != target_coords:
            raise ValueError(
                f"target rig coordinate convention differs from mapping: {actual_coords!r}"
            )
        target_names = {
            str(row.get("name"))
            for row in target_rig.get("restPose", {}).get("bones", [])
            if isinstance(row, dict)
        }
        unknown_targets = set(target_to_source) - target_names
        if unknown_targets:
            raise ValueError(f"mapping references target bones absent from target rig: {sorted(unknown_targets)}")
        missing_target = set(required_targets) - target_names
        if missing_target:
            raise ValueError(f"target rig lacks required mapped bones: {sorted(missing_target)}")

    return {
        "schema": MAPPING_SCHEMA,
        "version": MAPPING_VERSION,
        "id": mapping_id,
        "targetRig": target,
        "sourceCoordinateSystem": source_coords,
        "targetCoordinateSystem": target_coords,
        "sourceToTargetAxes": axes,
        "rootSourceBone": root_source_bone,
        "requiredTargets": required_targets,
        "targetToSource": target_to_source,
        "sourceToTarget": source_to_target,
        "poseErrorToleranceMeters": tolerance,
        "path": path,
    }


def load_target_and_mapping(target_rig_path: Path, mapping_path: Path) -> tuple[dict, dict]:
    target_rig = load_rig_profile(target_rig_path.resolve())
    mapping = load_mapping(mapping_path.resolve(), target_rig=target_rig)
    return target_rig, mapping
