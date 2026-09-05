from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from pathlib import Path
from typing import Any, Iterable, Sequence

from motion2sheet.motion.roundtrip.schema import validate_rig_document

SKIN_SCHEMA = "motion2sheet.skin"
SKIN_VERSION = 1
WEIGHT_SUM_TOLERANCE = 1e-6
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def _object(value: Any, label: str, required: set[str], optional: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    optional = optional or set()
    missing = required - set(value)
    extra = set(value) - required - optional
    if missing:
        raise ValueError(f"{label} missing fields: {sorted(missing)}")
    if extra:
        raise ValueError(f"{label} has unknown fields: {sorted(extra)}")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return 0.0 if result == 0.0 else result


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _matrix16(value: Any, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 16:
        raise ValueError(f"{label} must contain exactly 16 numbers")
    return [_number(item, f"{label}[{index}]") for index, item in enumerate(value)]


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def write_skin_document(path: Path, data: dict[str, Any], character_rig: dict[str, Any] | None = None) -> None:
    validated = validate_skin_document(data, character_rig)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(validated))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rig_fingerprint(rig: dict[str, Any]) -> str:
    validated = validate_rig_document(rig)
    authority = {
        "coordinateSystem": validated["coordinateSystem"],
        "bones": [
            {
                "name": bone["name"],
                "parent": bone["parent"],
                "editGeometry": bone["editGeometry"],
            }
            for bone in validated["bones"]
        ],
    }
    return hashlib.sha256(canonical_json_bytes(authority)).hexdigest()


def vertex_order_hash(vertices: Iterable[Sequence[float]]) -> str:
    rows = [tuple(_number(component, f"vertex[{index}]") for component in vertex) for index, vertex in enumerate(vertices)]
    if any(len(row) != 3 for row in rows):
        raise ValueError("every vertex must contain exactly 3 coordinates")
    digest = hashlib.sha256(b"motion2sheet.vertex-order.v1\0")
    digest.update(struct.pack("<Q", len(rows)))
    for index, row in enumerate(rows):
        digest.update(struct.pack("<Qddd", index, row[0], row[1], row[2]))
    return digest.hexdigest()


def normalize_influences(influences: Iterable[Sequence[Any]]) -> list[list[Any]]:
    rows: list[tuple[str, float]] = []
    seen: set[str] = set()
    for index, influence in enumerate(influences):
        if not isinstance(influence, (list, tuple)) or len(influence) != 2:
            raise ValueError(f"influence[{index}] must be [bone, weight]")
        bone = _string(influence[0], f"influence[{index}].bone")
        weight = _number(influence[1], f"influence[{index}].weight")
        if weight <= 0.0:
            raise ValueError(f"influence[{index}].weight must be > 0")
        if bone in seen:
            raise ValueError(f"duplicate influence bone: {bone}")
        seen.add(bone)
        rows.append((bone, weight))
    if not rows:
        raise ValueError("weighted vertex must contain at least one influence")
    total = sum(weight for _bone, weight in rows)
    if total <= 0.0:
        raise ValueError("influence weight total must be positive")
    return [[bone, weight / total] for bone, weight in sorted(rows, key=lambda item: item[0])]


def build_skin_document(
    *,
    skin_id: str,
    canonical_rig: str,
    character_rig: dict[str, Any],
    model: dict[str, Any],
    bind: dict[str, Any],
    meshes: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    validated_rig = validate_rig_document(character_rig)
    built_meshes: list[dict[str, Any]] = []
    referenced_bones: set[str] = set()
    for mesh in meshes:
        weights: list[dict[str, Any]] = []
        for row in mesh["weights"]:
            normalized = normalize_influences(row["influences"])
            referenced_bones.update(item[0] for item in normalized)
            weights.append({"vertex": _integer(row["vertex"], "skin build vertex"), "influences": normalized})
        weights.sort(key=lambda row: row["vertex"])
        built_meshes.append(
            {
                "object": mesh["object"],
                "vertexCount": _integer(mesh["vertexCount"], "skin build vertexCount", minimum=1),
                "vertexOrderHash": mesh["vertexOrderHash"],
                "objectTransform": list(mesh["objectTransform"]),
                "armatureModifier": dict(mesh["armatureModifier"]),
                "weights": weights,
            }
        )
    built_meshes.sort(key=lambda mesh: mesh["object"])
    document = {
        "schema": SKIN_SCHEMA,
        "version": SKIN_VERSION,
        "id": skin_id,
        "canonicalRig": canonical_rig,
        "rigFingerprint": rig_fingerprint(validated_rig),
        "model": model,
        "bind": bind,
        "boneTable": sorted(referenced_bones),
        "meshes": built_meshes,
    }
    return validate_skin_document(document, validated_rig)


def validate_skin_document(data: Any, character_rig: dict[str, Any] | None = None) -> dict[str, Any]:
    root = _object(
        data,
        "skin",
        {"schema", "version", "id", "canonicalRig", "rigFingerprint", "model", "bind", "boneTable", "meshes"},
    )
    if root["schema"] != SKIN_SCHEMA or root["version"] != SKIN_VERSION:
        raise ValueError("unsupported skin schema/version")
    if not isinstance(root["id"], str) or not _ID_RE.fullmatch(root["id"]):
        raise ValueError("skin.id has invalid format")
    _string(root["canonicalRig"], "skin.canonicalRig")
    _sha256(root["rigFingerprint"], "skin.rigFingerprint")

    model = _object(root["model"], "skin.model", {"filename", "format", "sha256", "coordinateSystem"})
    filename = _string(model["filename"], "skin.model.filename")
    if Path(filename).name != filename or Path(filename).suffix.lower() != ".glb":
        raise ValueError("skin.model.filename must be a basename ending in .glb")
    if model["format"] != "GLB":
        raise ValueError("skin.model.format must be GLB")
    _sha256(model["sha256"], "skin.model.sha256")
    if not isinstance(model["coordinateSystem"], dict) or not model["coordinateSystem"]:
        raise ValueError("skin.model.coordinateSystem must be a non-empty object")

    bind = _object(root["bind"], "skin.bind", {"mode", "restConvention", "armatureObject", "armatureObjectTransform"})
    if bind["mode"] != "blender-armature-modifier-v1":
        raise ValueError("skin.bind.mode must be blender-armature-modifier-v1")
    if bind["restConvention"] != "blender-edit-bone-y-axis-roll-v1":
        raise ValueError("skin.bind.restConvention is unsupported")
    armature_name = _string(bind["armatureObject"], "skin.bind.armatureObject")
    _matrix16(bind["armatureObjectTransform"], "skin.bind.armatureObjectTransform")

    bone_table = root["boneTable"]
    if not isinstance(bone_table, list):
        raise ValueError("skin.boneTable must be an array")
    normalized_bones = [_string(item, f"skin.boneTable[{index}]") for index, item in enumerate(bone_table)]
    if normalized_bones != sorted(normalized_bones) or len(set(normalized_bones)) != len(normalized_bones):
        raise ValueError("skin.boneTable must be unique and lexicographically sorted")
    bone_set = set(normalized_bones)

    meshes = root["meshes"]
    if not isinstance(meshes, list) or not meshes:
        raise ValueError("skin.meshes must be a non-empty array")
    mesh_names: list[str] = []
    for mesh_index, mesh_value in enumerate(meshes):
        mesh = _object(
            mesh_value,
            f"skin.meshes[{mesh_index}]",
            {"object", "vertexCount", "vertexOrderHash", "objectTransform", "armatureModifier", "weights"},
        )
        object_name = _string(mesh["object"], f"skin.meshes[{mesh_index}].object")
        mesh_names.append(object_name)
        vertex_count = _integer(mesh["vertexCount"], f"skin.meshes[{mesh_index}].vertexCount", minimum=1)
        _sha256(mesh["vertexOrderHash"], f"skin.meshes[{mesh_index}].vertexOrderHash")
        _matrix16(mesh["objectTransform"], f"skin.meshes[{mesh_index}].objectTransform")
        modifier = _object(mesh["armatureModifier"], f"skin.meshes[{mesh_index}].armatureModifier", {"name", "object"})
        _string(modifier["name"], f"skin.meshes[{mesh_index}].armatureModifier.name")
        if modifier["object"] != armature_name:
            raise ValueError(f"skin mesh {object_name} armature modifier must reference {armature_name!r}")
        weights = mesh["weights"]
        if not isinstance(weights, list):
            raise ValueError(f"skin mesh {object_name} weights must be an array")
        previous_vertex = -1
        for weight_index, row_value in enumerate(weights):
            row = _object(row_value, f"skin mesh {object_name} weights[{weight_index}]", {"vertex", "influences"})
            vertex = _integer(row["vertex"], f"skin mesh {object_name} weights[{weight_index}].vertex")
            if vertex >= vertex_count:
                raise ValueError(f"skin mesh {object_name} references vertex {vertex} >= {vertex_count}")
            if vertex <= previous_vertex:
                raise ValueError(f"skin mesh {object_name} weighted vertices must be strictly increasing")
            previous_vertex = vertex
            influences = row["influences"]
            if not isinstance(influences, list) or not influences:
                raise ValueError(f"skin mesh {object_name} vertex {vertex} must have influences")
            names: list[str] = []
            total = 0.0
            for influence_index, influence in enumerate(influences):
                if not isinstance(influence, list) or len(influence) != 2:
                    raise ValueError(f"skin mesh {object_name} vertex {vertex} influence[{influence_index}] must be [bone, weight]")
                bone = _string(influence[0], f"skin mesh {object_name} vertex {vertex} influence[{influence_index}].bone")
                weight = _number(influence[1], f"skin mesh {object_name} vertex {vertex} influence[{influence_index}].weight")
                if weight <= 0.0:
                    raise ValueError(f"skin mesh {object_name} vertex {vertex} influence weight must be > 0")
                if bone not in bone_set:
                    raise ValueError(f"skin mesh {object_name} vertex {vertex} references bone outside boneTable: {bone}")
                names.append(bone)
                total += weight
            if names != sorted(names) or len(set(names)) != len(names):
                raise ValueError(f"skin mesh {object_name} vertex {vertex} influences must be unique and sorted")
            if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
                raise ValueError(f"skin mesh {object_name} vertex {vertex} weights sum to {total:.12g}, expected 1")
    if mesh_names != sorted(mesh_names) or len(set(mesh_names)) != len(mesh_names):
        raise ValueError("skin.meshes must have unique lexicographically sorted object names")

    if character_rig is not None:
        rig = validate_rig_document(character_rig)
        rig_names = {bone["name"] for bone in rig["bones"]}
        unknown = sorted(bone_set - rig_names)
        if unknown:
            raise ValueError(f"skin references unknown character-rig bones: {unknown}")
        expected_fingerprint = rig_fingerprint(rig)
        if root["rigFingerprint"] != expected_fingerprint:
            raise ValueError("skin.rigFingerprint does not match character rig")
        if model["coordinateSystem"] != rig["coordinateSystem"]:
            raise ValueError("skin model coordinate convention does not match character rig")
    return root


def skin_statistics(data: dict[str, Any], character_rig: dict[str, Any] | None = None) -> dict[str, int]:
    skin = validate_skin_document(data, character_rig)
    return {
        "meshCount": len(skin["meshes"]),
        "vertexCount": sum(mesh["vertexCount"] for mesh in skin["meshes"]),
        "weightedVertexCount": sum(len(mesh["weights"]) for mesh in skin["meshes"]),
        "influenceCount": sum(len(row["influences"]) for mesh in skin["meshes"] for row in mesh["weights"]),
        "boneCount": len(skin["boneTable"]),
        "unknownBoneReferences": 0,
    }


def verify_model_identity(data: dict[str, Any], model_path: Path, mesh_layout: Iterable[dict[str, Any]]) -> None:
    skin = validate_skin_document(data)
    if file_sha256(model_path) != skin["model"]["sha256"]:
        raise ValueError("model asset SHA-256 does not match skin contract")
    expected = {mesh["object"]: mesh for mesh in skin["meshes"]}
    actual: dict[str, dict[str, Any]] = {}
    for row in mesh_layout:
        name = _string(row.get("object"), "model mesh object")
        if name in actual:
            raise ValueError(f"duplicate model mesh object: {name}")
        actual[name] = row
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    if missing or extra:
        raise ValueError(f"model mesh set mismatch: missing={missing} extra={extra}")
    for name in sorted(expected):
        if actual[name].get("vertexCount") != expected[name]["vertexCount"]:
            raise ValueError(f"model vertex count mismatch for {name}")
        if actual[name].get("vertexOrderHash") != expected[name]["vertexOrderHash"]:
            raise ValueError(f"model vertex-order hash mismatch for {name}")


def compare_skin_bindings(reference: dict[str, Any], reconstructed: dict[str, Any], *, tolerance: float = 1e-8) -> dict[str, Any]:
    if tolerance < 0.0:
        raise ValueError("skin comparison tolerance must be non-negative")
    first = validate_skin_document(reference)
    second = validate_skin_document(reconstructed)
    first_meshes = {mesh["object"]: mesh for mesh in first["meshes"]}
    second_meshes = {mesh["object"]: mesh for mesh in second["meshes"]}
    if set(first_meshes) != set(second_meshes):
        raise ValueError(
            f"skin mesh set mismatch: reference={sorted(first_meshes)} reconstructed={sorted(second_meshes)}"
        )

    max_delta = 0.0
    worst: dict[str, Any] | None = None
    weighted_vertices = 0
    influence_count = 0
    for mesh_name in sorted(first_meshes):
        expected = first_meshes[mesh_name]
        actual = second_meshes[mesh_name]
        if expected["vertexCount"] != actual["vertexCount"]:
            raise ValueError(f"skin vertex count mismatch for {mesh_name}")
        if expected["vertexOrderHash"] != actual["vertexOrderHash"]:
            raise ValueError(f"skin vertex-order hash mismatch for {mesh_name}")
        expected_rows = {row["vertex"]: row for row in expected["weights"]}
        actual_rows = {row["vertex"]: row for row in actual["weights"]}
        if set(expected_rows) != set(actual_rows):
            raise ValueError(f"skin weighted-vertex set mismatch for {mesh_name}")
        weighted_vertices += len(expected_rows)
        for vertex in sorted(expected_rows):
            expected_weights = {bone: float(weight) for bone, weight in expected_rows[vertex]["influences"]}
            actual_weights = {bone: float(weight) for bone, weight in actual_rows[vertex]["influences"]}
            if set(expected_weights) != set(actual_weights):
                raise ValueError(f"skin influenced-bone set mismatch for {mesh_name} vertex {vertex}")
            influence_count += len(expected_weights)
            for bone in sorted(expected_weights):
                delta = abs(expected_weights[bone] - actual_weights[bone])
                if delta > max_delta:
                    max_delta = delta
                    worst = {"mesh": mesh_name, "vertex": vertex, "bone": bone, "delta": delta}

    return {
        "pass": max_delta <= tolerance,
        "meshCount": len(first_meshes),
        "weightedVertexCount": weighted_vertices,
        "influenceCount": influence_count,
        "sameMeshObjects": True,
        "sameVertexCounts": True,
        "sameVertexOrder": True,
        "sameInfluencedBones": True,
        "tolerance": tolerance,
        "maxWeightDelta": max_delta,
        "worst": worst,
    }
