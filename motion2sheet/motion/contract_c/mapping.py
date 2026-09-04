from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from motion2sheet.motion.roundtrip.schema import validate_rig_document

from .schema import CANONICAL_SKELETON, CANONICAL_SKELETON_ID, MAPPED_JOINTS

MAPPING_SCHEMA = "motion2sheet.contract-c.character-map"


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
        "leftRightIdentity": all(joints[f"Left{suffix}"] != joints[f"Right{suffix}"] for suffix in (
            "Shoulder", "UpperArm", "LowerArm", "Hand", "UpperLeg", "LowerLeg", "Foot", "Toe"
        )),
    }
