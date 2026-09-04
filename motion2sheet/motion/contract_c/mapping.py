from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from motion2sheet.motion.roundtrip.schema import validate_rig_document

from .schema import CANONICAL_SKELETON, CANONICAL_SKELETON_ID, MAPPED_JOINTS

MAPPING_SCHEMA = "motion2sheet.contract-c.character-map"
LEFT_RIGHT_TOLERANCE = 1e-6
LEFT_RIGHT_SUFFIXES = (
    "Shoulder", "UpperArm", "LowerArm", "Hand", "UpperLeg", "LowerLeg", "Foot", "Toe",
)


def _rotate_vector(quaternion: list[float], vector: list[float]) -> list[float]:
    w, x, y, z = quaternion
    norm = math.sqrt(sum(value * value for value in quaternion))
    w, x, y, z = (value / norm for value in (w, x, y, z))
    vx, vy, vz = vector
    tx, ty, tz = 2.0 * (y * vz - z * vy), 2.0 * (z * vx - x * vz), 2.0 * (x * vy - y * vx)
    return [
        vx + w * tx + (y * tz - z * ty),
        vy + w * ty + (z * tx - x * tz),
        vz + w * tz + (x * ty - y * tx),
    ]


def _world_head(bone: dict[str, Any], rig: dict[str, Any]) -> list[float]:
    transform = rig["armatureObject"]["transform"]
    scaled = [
        float(bone["editGeometry"]["head"][index]) * float(transform["scale"][index])
        for index in range(3)
    ]
    rotated = _rotate_vector([float(value) for value in transform["rotationQuaternion"]], scaled)
    return [rotated[index] + float(transform["translation"][index]) for index in range(3)]


def left_right_diagnostics(joints: dict[str, str], bones: dict[str, dict[str, Any]], rig: dict[str, Any]) -> dict[str, Any]:
    pairs = []
    for suffix in LEFT_RIGHT_SUFFIXES:
        left_name = joints[f"Left{suffix}"]
        right_name = joints[f"Right{suffix}"]
        left_x = _world_head(bones[left_name], rig)[0]
        right_x = _world_head(bones[right_name], rig)[0]
        pairs.append({
            "semanticPair": suffix,
            "leftBone": left_name,
            "rightBone": right_name,
            "leftX": left_x,
            "rightX": right_x,
            "pass": left_name != right_name and left_x > right_x + LEFT_RIGHT_TOLERANCE,
        })
    return {
        "pass": all(row["pass"] for row in pairs),
        "rightAxis": "+X",
        "tolerance": LEFT_RIGHT_TOLERANCE,
        "pairs": pairs,
    }


def read_mapping(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_character_mapping(value: Any, rig: dict[str, Any]) -> dict[str, Any]:
    rig = validate_rig_document(rig)
    if not isinstance(value, dict):
        raise ValueError("Contract C character mapping must be an object")
    required = {"schema", "version", "id", "canonicalSkeleton", "joints"}
    missing_fields = required - set(value)
    unknown_fields = set(value) - required
    if missing_fields or unknown_fields:
        raise ValueError(f"mapping fields mismatch; missing={sorted(missing_fields)} extra={sorted(unknown_fields)}")
    if value["schema"] != MAPPING_SCHEMA or value["version"] != 1:
        raise ValueError("unsupported Contract C mapping schema/version")
    if not isinstance(value["id"], str) or not value["id"]:
        raise ValueError("mapping.id must be a non-empty string")
    if value["canonicalSkeleton"] != CANONICAL_SKELETON_ID:
        raise ValueError(f"mapping canonicalSkeleton must be {CANONICAL_SKELETON_ID!r}")
    joints = value["joints"]
    if not isinstance(joints, dict) or set(joints) != set(MAPPED_JOINTS):
        absent = set(MAPPED_JOINTS) - set(joints or {})
        extra = set(joints or {}) - set(MAPPED_JOINTS)
        raise ValueError(f"mapping semantic set mismatch; missing={sorted(absent)} extra={sorted(extra)}")
    if any(not isinstance(name, str) or not name for name in joints.values()):
        raise ValueError("mapping target bone names must be non-empty strings")
    if len(set(joints.values())) != len(joints):
        raise ValueError("mapping must map each semantic to a distinct target bone")

    bones = {bone["name"]: bone for bone in rig["bones"]}
    absent_bones = sorted(set(joints.values()) - set(bones))
    if absent_bones:
        raise ValueError(f"mapping references bones absent from character rig: {absent_bones}")

    def ancestors(name: str) -> list[str]:
        result: list[str] = []
        current = bones[name]["parent"]
        seen = set()
        while current is not None:
            if current in seen or current not in bones:
                raise ValueError(f"invalid target hierarchy while mapping {name!r}")
            result.append(current)
            seen.add(current)
            current = bones[current]["parent"]
        return result

    for semantic in MAPPED_JOINTS:
        parent_semantic = CANONICAL_SKELETON[semantic]
        if parent_semantic == "Root":
            continue
        bone = joints[semantic]
        parent_bone = joints[parent_semantic]
        chain = ancestors(bone)
        if parent_bone not in chain:
            raise ValueError(
                f"mapping hierarchy mismatch: {parent_semantic}->{semantic} must map to an ancestor path; "
                f"got {parent_bone!r}->{bone!r}"
            )
    left_right = left_right_diagnostics(joints, bones, rig)
    if not left_right["pass"]:
        failed = [row["semanticPair"] for row in left_right["pairs"] if not row["pass"]]
        raise ValueError(f"mapping left/right geometry mismatch on canonical +X axis: {failed}")
    return value


def mapping_diagnostics(value: dict[str, Any], rig: dict[str, Any]) -> dict[str, Any]:
    mapping = validate_character_mapping(value, rig)
    bones = {bone["name"]: bone for bone in rig["bones"]}
    joints = mapping["joints"]

    def ancestors(name: str) -> list[str]:
        result = []
        current = bones[name]["parent"]
        while current is not None:
            result.append(current)
            current = bones[current]["parent"]
        return result

    bridge_helpers: set[str] = set()
    for semantic in MAPPED_JOINTS:
        parent_semantic = CANONICAL_SKELETON[semantic]
        if parent_semantic == "Root":
            continue
        chain = ancestors(joints[semantic])
        parent_bone = joints[parent_semantic]
        bridge_helpers.update(candidate for candidate in chain[:chain.index(parent_bone)] if candidate not in joints.values())
    mapped_bones = set(joints.values())
    return {
        "schema": "motion2sheet.contract-c.diagnostics.semantic-mapping",
        "version": 1,
        "mappingId": mapping["id"],
        "canonicalSkeleton": CANONICAL_SKELETON_ID,
        "mappedJointCount": len(joints),
        "mappedJoints": dict(sorted(joints.items())),
        "missingRequiredJoints": [],
        "bridgeHelperBones": sorted(bridge_helpers),
        "ignoredBones": sorted(set(bones) - mapped_bones),
        "leftRightIdentity": True,
        "leftRightVerification": left_right_diagnostics(joints, bones, rig),
    }
