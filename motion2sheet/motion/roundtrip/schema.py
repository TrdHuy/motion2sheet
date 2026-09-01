from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

RIG_SCHEMA = "motion2sheet.source-rig"
ANIMATION_SCHEMA = "motion2sheet.source-animation"
VERSION = 1
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
STACK_TIMING_FIELDS = ("LocalStart", "LocalStop", "ReferenceStart", "ReferenceStop")


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return 0.0 if value == 0.0 else value


def vec(values: Any, size: int, label: str) -> list[float]:
    if not isinstance(values, list) or len(values) != size:
        raise ValueError(f"{label} must contain exactly {size} numbers")
    return [_finite(value, f"{label}[{index}]") for index, value in enumerate(values)]


def validate_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ValueError(f"{label} must match {ID_RE.pattern}")
    return value


def validate_trs(data: Any, label: str) -> None:
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be an object")
    expected = {"translation", "rotationQuaternion", "scale"}
    unknown = set(data) - expected
    if unknown:
        raise ValueError(f"{label} has unknown fields: {sorted(unknown)}")
    missing = expected - set(data)
    if missing:
        raise ValueError(f"{label} missing fields: {sorted(missing)}")
    vec(data["translation"], 3, f"{label}.translation")
    quaternion = vec(data["rotationQuaternion"], 4, f"{label}.rotationQuaternion")
    norm = math.sqrt(sum(value * value for value in quaternion))
    if abs(norm - 1.0) > 1e-8:
        raise ValueError(f"{label}.rotationQuaternion must be normalized; norm={norm}")
    vec(data["scale"], 3, f"{label}.scale")


def validate_edit_geometry(data: Any, label: str) -> None:
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be an object")
    expected = {"head", "tail", "roll"}
    unknown = set(data) - expected
    if unknown:
        raise ValueError(f"{label} has unknown fields: {sorted(unknown)}")
    missing = expected - set(data)
    if missing:
        raise ValueError(f"{label} missing fields: {sorted(missing)}")
    head = vec(data["head"], 3, f"{label}.head")
    tail = vec(data["tail"], 3, f"{label}.tail")
    _finite(data["roll"], f"{label}.roll")
    length = math.sqrt(sum((a - b) ** 2 for a, b in zip(head, tail)))
    if length <= 1e-12:
        raise ValueError(f"{label} head/tail must define a non-zero bone")


_FBX_VECTOR_STACK_FIELDS = (
    "Lcl Translation",
    "Lcl Rotation",
    "Lcl Scaling",
    "PreRotation",
    "PostRotation",
    "RotationOffset",
    "RotationPivot",
    "ScalingOffset",
    "ScalingPivot",
)


def _validate_matrix16(values: Any, label: str) -> None:
    vec(values, 16, label)


def _validate_fbx_encoding_adapter(data: Any, label: str) -> None:
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be an object")
    expected = {"preMatrix", "postMatrix", "geometryMatrix", "rotationAltMatrix"}
    if set(data) != expected:
        raise ValueError(f"{label} fields must be {sorted(expected)}")
    for field in sorted(expected):
        _validate_matrix16(data[field], f"{label}.{field}")


def _validate_fbx_rig_metadata(data: Any, rig_bones: set[str]) -> None:
    if not isinstance(data, dict):
        raise ValueError("rig.sourceFormat.fbx must be an object")
    expected_top = {"fbxVersion", "globalSettings", "bones"}
    if set(data) != expected_top:
        raise ValueError(f"rig.sourceFormat.fbx fields must be {sorted(expected_top)}")
    version = data.get("fbxVersion")
    if not isinstance(version, int) or isinstance(version, bool) or version < 7000:
        raise ValueError("rig.sourceFormat.fbx.fbxVersion must be an FBX 7.x+ integer")
    settings = data.get("globalSettings")
    if not isinstance(settings, dict) or not settings:
        raise ValueError("rig.sourceFormat.fbx.globalSettings must be a non-empty object")
    for key, value in settings.items():
        if not isinstance(key, str) or not key:
            raise ValueError("rig.sourceFormat.fbx.globalSettings keys must be non-empty strings")
        _finite(value, f"rig.sourceFormat.fbx.globalSettings.{key}")
    bones = data.get("bones")
    if not isinstance(bones, dict) or set(bones) != rig_bones:
        missing = rig_bones - set(bones or {})
        extra = set(bones or {}) - rig_bones
        raise ValueError(f"rig.sourceFormat.fbx bone set mismatch; missing={sorted(missing)} extra={sorted(extra)}")
    for bone_name, payload in bones.items():
        if not isinstance(payload, dict):
            raise ValueError(f"FBX metadata for {bone_name} must be an object")
        if set(payload) - {"transformStack", "encodingAdapter"}:
            raise ValueError(f"FBX metadata for {bone_name} has unknown fields: {sorted(set(payload) - {'transformStack', 'encodingAdapter'})}")
        if "transformStack" not in payload:
            raise ValueError(f"FBX metadata for {bone_name} must contain transformStack")
        stack = payload["transformStack"]
        if not isinstance(stack, dict):
            raise ValueError(f"FBX transformStack for {bone_name} must be an object")
        for field in _FBX_VECTOR_STACK_FIELDS:
            vec(stack.get(field), 3, f"FBX {bone_name}.{field}")
        rotation_order = stack.get("RotationOrder")
        if not isinstance(rotation_order, int) or isinstance(rotation_order, bool) or not 0 <= rotation_order <= 6:
            raise ValueError(f"FBX {bone_name}.RotationOrder must be an integer in 0..6")
        if not isinstance(stack.get("RotationActive"), bool):
            raise ValueError(f"FBX {bone_name}.RotationActive must be boolean")
        if "InheritType" in stack:
            inherit_type = stack["InheritType"]
            if not isinstance(inherit_type, int) or isinstance(inherit_type, bool):
                raise ValueError(f"FBX {bone_name}.InheritType must be an integer")
        if "encodingAdapter" in payload:
            _validate_fbx_encoding_adapter(payload["encodingAdapter"], f"FBX {bone_name}.encodingAdapter")


def _validate_fbx_animation_metadata(data: Any, expected_frame_count: int) -> None:
    if not isinstance(data, dict):
        raise ValueError("animation.sourceFormat.fbx must be an object")
    expected = {"stack", "layer", "stackTiming", "sampling", "sampleKeyTimes"}
    if set(data) != expected:
        extra = set(data) - expected
        if "curves" in extra:
            raise ValueError(
                "animation.sourceFormat.fbx.curves is forbidden: animation.frames is the sole motion authority"
            )
        raise ValueError(f"animation.sourceFormat.fbx fields must be {sorted(expected)}")
    if not isinstance(data.get("stack"), str) or not data["stack"]:
        raise ValueError("animation.sourceFormat.fbx.stack must be non-empty")
    if not isinstance(data.get("layer"), str) or not data["layer"]:
        raise ValueError("animation.sourceFormat.fbx.layer must be non-empty")
    if data.get("sampling") != "all-integer-source-frames":
        raise ValueError("animation.sourceFormat.fbx.sampling must be 'all-integer-source-frames'")
    stack_timing = data.get("stackTiming")
    if not isinstance(stack_timing, dict) or set(stack_timing) != set(STACK_TIMING_FIELDS):
        raise ValueError(f"animation.sourceFormat.fbx.stackTiming fields must be {sorted(STACK_TIMING_FIELDS)}")
    for field in STACK_TIMING_FIELDS:
        value = stack_timing[field]
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"animation.sourceFormat.fbx.stackTiming.{field} must be an integer KTime")
    sample_key_times = data.get("sampleKeyTimes")
    if (
        not isinstance(sample_key_times, list)
        or len(sample_key_times) != expected_frame_count
        or not all(isinstance(value, int) and not isinstance(value, bool) for value in sample_key_times)
    ):
        raise ValueError(
            "animation.sourceFormat.fbx.sampleKeyTimes must contain one integer KTime per source frame"
        )
    if any(right <= left for left, right in zip(sample_key_times, sample_key_times[1:])):
        raise ValueError("animation.sourceFormat.fbx.sampleKeyTimes must be strictly increasing")


def validate_rig_document(data: Any) -> dict:
    if not isinstance(data, dict):
        raise ValueError("rig document must be an object")
    if data.get("schema") != RIG_SCHEMA or data.get("version") != VERSION:
        raise ValueError(f"unsupported rig schema/version: {data.get('schema')!r}/{data.get('version')!r}")
    validate_id(data.get("id"), "rig.id")
    if data.get("editGeometrySpace") != "armature-local":
        raise ValueError("rig.editGeometrySpace must be 'armature-local'")
    validate_trs(data.get("armatureObject", {}).get("transform"), "rig.armatureObject.transform")
    bones = data.get("bones")
    if not isinstance(bones, list) or not bones:
        raise ValueError("rig.bones must be a non-empty list")
    names: set[str] = set()
    for index, bone in enumerate(bones):
        if not isinstance(bone, dict):
            raise ValueError(f"rig.bones[{index}] must be an object")
        name = bone.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError(f"rig.bones[{index}].name must be non-empty")
        if name in names:
            raise ValueError(f"duplicate bone name: {name}")
        names.add(name)
        parent = bone.get("parent")
        if parent is not None and not isinstance(parent, str):
            raise ValueError(f"bone {name}.parent must be string or null")
        validate_trs(bone.get("rest"), f"bone {name}.rest")
        validate_edit_geometry(bone.get("editGeometry"), f"bone {name}.editGeometry")
        length = _finite(bone.get("length"), f"bone {name}.length")
        if length <= 0:
            raise ValueError(f"bone {name}.length must be positive")
    for bone in bones:
        parent = bone.get("parent")
        if parent is not None and parent not in names:
            raise ValueError(f"bone {bone['name']} references missing parent {parent}")
    source = data.get("source")
    if isinstance(source, dict) and source.get("format") == "FBX":
        source_format = data.get("sourceFormat")
        if not isinstance(source_format, dict) or set(source_format) != {"fbx"}:
            raise ValueError("FBX rig must contain sourceFormat.fbx")
        _validate_fbx_rig_metadata(source_format["fbx"], names)
    return data


def validate_animation_document(data: Any, rig: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("animation document must be an object")
    if data.get("schema") != ANIMATION_SCHEMA or data.get("version") != VERSION:
        raise ValueError(f"unsupported animation schema/version: {data.get('schema')!r}/{data.get('version')!r}")
    validate_id(data.get("id"), "animation.id")
    rig_ref = data.get("rig")
    if not isinstance(rig_ref, dict) or rig_ref.get("id") != rig.get("id"):
        raise ValueError("animation.rig.id must match rig.id")
    fps = _finite(data.get("fps"), "animation.fps")
    if fps <= 0:
        raise ValueError("animation.fps must be positive")
    frame_range = data.get("frameRange")
    if not isinstance(frame_range, list) or len(frame_range) != 2 or not all(isinstance(v, int) and not isinstance(v, bool) for v in frame_range):
        raise ValueError("animation.frameRange must be [integerStart, integerEnd]")
    start, end = frame_range
    if end < start:
        raise ValueError("animation.frameRange end must be >= start")
    frames = data.get("frames")
    if not isinstance(frames, list) or not frames:
        raise ValueError("animation.frames must be non-empty")
    expected_frames = list(range(start, end + 1))
    actual_frames = [entry.get("frame") if isinstance(entry, dict) else None for entry in frames]
    if actual_frames != expected_frames:
        raise ValueError(f"animation.frames must be ordered and contiguous: expected {expected_frames[0]}..{expected_frames[-1]}")
    if data.get("frameCount") != len(expected_frames):
        raise ValueError("animation.frameCount contradicts frameRange")
    rig_bones = {bone["name"] for bone in rig["bones"]}
    for entry in frames:
        bones = entry.get("bones")
        if not isinstance(bones, dict) or set(bones) != rig_bones:
            missing = rig_bones - set(bones or {})
            extra = set(bones or {}) - rig_bones
            raise ValueError(f"frame {entry.get('frame')} bone set mismatch; missing={sorted(missing)} extra={sorted(extra)}")
        for bone_name, transform in bones.items():
            validate_trs(transform, f"frame {entry['frame']} bone {bone_name}")
    source = data.get("source")
    if isinstance(source, dict) and source.get("format") == "FBX":
        source_format = data.get("sourceFormat")
        if not isinstance(source_format, dict) or set(source_format) != {"fbx"}:
            raise ValueError("FBX animation must contain sourceFormat.fbx")
        _validate_fbx_animation_metadata(source_format["fbx"], len(expected_frames))
    return data


def canonical_json_text(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False, separators=(",", ": ")) + "\n"


def write_canonical_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json_text(data), encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
