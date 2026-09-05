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
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
STACK_TIMING_FIELDS = ("LocalStart", "LocalStop", "ReferenceStart", "ReferenceStop")
DURATION_TOLERANCE_SECONDS = 1e-6

# editGeometry is captured through Blender EditBone float32 state, while Bone.matrix_local
# is independently materialized by Blender. The two representations can differ by a few
# 1e-4 units/rotation-matrix elements after FBX import/edit-mode conversion. This
# tolerance is ONLY for checking the derived rig cache; round-trip acceptance tolerances
# remain unchanged in blender_verify.py.
DERIVED_REST_TOLERANCE = 5e-4
DERIVED_LENGTH_TOLERANCE = 5e-4


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return 0.0 if value == 0.0 else value


def _expect_object(
    data: Any,
    label: str,
    required: set[str],
    optional: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be an object")
    optional = optional or set()
    allowed = required | optional
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"{label} has unknown fields: {sorted(unknown)}")
    missing = required - set(data)
    if missing:
        raise ValueError(f"{label} missing fields: {sorted(missing)}")
    return data


def _non_empty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _integer(value: Any, label: str) -> int:
    # bool is a subclass of int in Python, so check it explicitly. JSON integer
    # fields are intentionally type-strict: true/false and 1.0 are not integers.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def vec(values: Any, size: int, label: str) -> list[float]:
    if not isinstance(values, list) or len(values) != size:
        raise ValueError(f"{label} must contain exactly {size} numbers")
    return [_finite(value, f"{label}[{index}]") for index, value in enumerate(values)]


def validate_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ValueError(f"{label} must match {ID_RE.pattern}")
    return value


def _validate_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase 64-character SHA-256")
    return value


def validate_trs(data: Any, label: str) -> None:
    expected = {"translation", "rotationQuaternion", "scale"}
    _expect_object(data, label, expected)
    vec(data["translation"], 3, f"{label}.translation")
    quaternion = vec(data["rotationQuaternion"], 4, f"{label}.rotationQuaternion")
    norm = math.sqrt(sum(value * value for value in quaternion))
    if abs(norm - 1.0) > 1e-8:
        raise ValueError(f"{label}.rotationQuaternion must be normalized; norm={norm}")
    vec(data["scale"], 3, f"{label}.scale")


def validate_edit_geometry(data: Any, label: str) -> None:
    expected = {"head", "tail", "roll"}
    _expect_object(data, label, expected)
    head = vec(data["head"], 3, f"{label}.head")
    tail = vec(data["tail"], 3, f"{label}.tail")
    _finite(data["roll"], f"{label}.roll")
    length = math.sqrt(sum((a - b) ** 2 for a, b in zip(head, tail)))
    if length <= 1e-12:
        raise ValueError(f"{label} head/tail must define a non-zero bone")


def _mat3_mul(first: list[list[float]], second: list[list[float]]) -> list[list[float]]:
    return [
        [sum(first[row][k] * second[k][column] for k in range(3)) for column in range(3)]
        for row in range(3)
    ]


def _mat3_transpose(matrix: list[list[float]]) -> list[list[float]]:
    return [[matrix[column][row] for column in range(3)] for row in range(3)]


def _mat3_vec_mul(matrix: list[list[float]], vector: list[float]) -> list[float]:
    return [sum(matrix[row][column] * vector[column] for column in range(3)) for row in range(3)]


def _axis_angle_matrix(axis: list[float], angle: float) -> list[list[float]]:
    x, y, z = axis
    cosine = math.cos(angle)
    sine = math.sin(angle)
    one_minus = 1.0 - cosine
    return [
        [
            one_minus * x * x + cosine,
            one_minus * x * y - sine * z,
            one_minus * x * z + sine * y,
        ],
        [
            one_minus * x * y + sine * z,
            one_minus * y * y + cosine,
            one_minus * y * z - sine * x,
        ],
        [
            one_minus * x * z - sine * y,
            one_minus * y * z + sine * x,
            one_minus * z * z + cosine,
        ],
    ]


def _vec_roll_to_mat3(vector: list[float], roll: float) -> list[list[float]]:
    """Pure-Python equivalent of Blender BKE vec_roll_to_mat3 for validation."""

    length = math.sqrt(sum(value * value for value in vector))
    if length <= 1e-12:
        raise ValueError("editGeometry bone vector must be non-zero")
    x, y, z = [value / length for value in vector]
    theta = 1.0 + y
    theta_alt = x * x + z * z
    safe_threshold = 6.1e-3
    critical_threshold = 2.5e-4

    if theta > safe_threshold or theta_alt > critical_threshold * critical_threshold:
        if theta <= safe_threshold:
            theta = theta_alt * 0.5 + theta_alt * theta_alt * 0.125
        base = [
            [1.0 - x * x / theta, x, -x * z / theta],
            [-x, y, -z],
            [-x * z / theta, z, 1.0 - z * z / theta],
        ]
    else:
        base = [
            [-1.0, 0.0, 0.0],
            [0.0, -1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]

    roll_matrix = _axis_angle_matrix([x, y, z], roll)
    return _mat3_mul(roll_matrix, base)


def _quaternion_matrix(values: list[float]) -> list[list[float]]:
    w, x, y, z = values
    norm = math.sqrt(w * w + x * x + y * y + z * z)
    if norm <= 1e-15:
        raise ValueError("quaternion must be non-zero")
    w, x, y, z = [value / norm for value in (w, x, y, z)]
    return [
        [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
        [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
        [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
    ]


def _geometry_basis(geometry: dict[str, Any]) -> tuple[list[list[float]], list[float], float]:
    head = [float(value) for value in geometry["head"]]
    tail = [float(value) for value in geometry["tail"]]
    vector = [tail[index] - head[index] for index in range(3)]
    length = math.sqrt(sum(value * value for value in vector))
    return _vec_roll_to_mat3(vector, float(geometry["roll"])), head, length


def _validate_derived_rest_cache(bones: list[dict[str, Any]]) -> None:
    """Ensure rest/length cannot disagree with canonical editGeometry.

    editGeometry is the sole rest authority. `rest` and `length` are retained
    as convenience caches for inspection/verifier reporting. Blender FBX import
    and EditBone conversion are float32 operations, so this invariant uses a
    dedicated cache-consistency tolerance, separate from round-trip gates.
    """

    absolute_geometry: dict[str, tuple[list[list[float]], list[float], float]] = {}
    for bone in bones:
        absolute_geometry[bone["name"]] = _geometry_basis(bone["editGeometry"])

    for bone in bones:
        name = bone["name"]
        child_rotation, child_head, geometry_length = absolute_geometry[name]
        parent_name = bone["parent"]
        if parent_name is None:
            expected_rotation = child_rotation
            expected_translation = child_head
        else:
            parent_rotation, parent_head, _parent_length = absolute_geometry[parent_name]
            parent_inverse_rotation = _mat3_transpose(parent_rotation)
            expected_rotation = _mat3_mul(parent_inverse_rotation, child_rotation)
            expected_translation = _mat3_vec_mul(
                parent_inverse_rotation,
                [child_head[index] - parent_head[index] for index in range(3)],
            )

        rest = bone["rest"]
        rest_rotation = _quaternion_matrix([float(value) for value in rest["rotationQuaternion"]])
        scales = [float(value) for value in rest["scale"]]
        rest_linear = [
            [rest_rotation[row][column] * scales[column] for column in range(3)]
            for row in range(3)
        ]
        linear_error = max(
            abs(rest_linear[row][column] - expected_rotation[row][column])
            for row in range(3)
            for column in range(3)
        )
        translation_error = max(
            abs(float(rest["translation"][index]) - expected_translation[index])
            for index in range(3)
        )
        length_error = abs(float(bone["length"]) - geometry_length)
        cache_error = max(linear_error, translation_error)
        if cache_error > DERIVED_REST_TOLERANCE or length_error > DERIVED_LENGTH_TOLERANCE:
            raise ValueError(
                f"bone {name} derived rest cache conflicts with canonical editGeometry: "
                f"matrix/translationError={cache_error:.12g} "
                f"lengthError={length_error:.12g}; "
                f"tolerances={DERIVED_REST_TOLERANCE:.12g}/{DERIVED_LENGTH_TOLERANCE:.12g}"
            )


_BONE_PROPERTY_REQUIRED = {
    "useConnect",
    "useDeform",
    "useInheritRotation",
    "useLocalLocation",
    "inheritScale",
    "headRadius",
    "tailRadius",
    "envelopeDistance",
    "envelopeWeight",
}
_BONE_PROPERTY_OPTIONAL = {"useRelativeParent"}


def _validate_bone_properties(data: Any, label: str) -> None:
    _expect_object(data, label, _BONE_PROPERTY_REQUIRED, _BONE_PROPERTY_OPTIONAL)
    for field in ("useConnect", "useDeform", "useInheritRotation", "useLocalLocation"):
        _boolean(data[field], f"{label}.{field}")
    if "useRelativeParent" in data:
        _boolean(data["useRelativeParent"], f"{label}.{useRelativeParent}")
    _non_empty_string(data["inheritScale"], f"{label}.inheritScale")
    for field in ("headRadius", "tailRadius", "envelopeDistance", "envelopeWeight"):
        _finite(data[field], f"{label}.{field}")


def _validate_source(data: Any, label: str, *, animation: bool) -> str:
    required = {"format", "filename", "sha256", "action"} if animation else {
        "format",
        "filename",
        "sha256",
        "importer",
    }
    _expect_object(data, label, required)
    source_format = _non_empty_string(data["format"], f"{label}.format")
    if source_format not in {"FBX", "BVH"}:
        raise ValueError(f"{label}.format must be FBX or BVH")
    _non_empty_string(data["filename"], f"{label}.filename")
    _validate_sha256(data["sha256"], f"{label}.sha256")
    if animation:
        _non_empty_string(data["action"], f"{label}.action")
    else:
        importer = _non_empty_string(data["importer"], f"{label}.importer")
        expected_importer = "blender-fbx" if source_format == "FBX" else "blender-bvh"
        if importer != expected_importer:
            raise ValueError(f"{label}.importer must be {expected_importer!r} for {source_format}")
    return source_format


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
_FBX_GLOBAL_SETTINGS_FIELDS = {
    "UpAxis",
    "UpAxisSign",
    "FrontAxis",
    "FrontAxisSign",
    "CoordAxis",
    "CoordAxisSign",
    "UnitScaleFactor",
    "OriginalUnitScaleFactor",
    "TimeMode",
    "CustomFrameRate",
}


def _validate_matrix16(values: Any, label: str) -> None:
    vec(values, 16, label)


def _validate_fbx_encoding_adapter(data: Any, label: str) -> None:
    expected = {"preMatrix", "postMatrix", "geometryMatrix", "rotationAltMatrix"}
    _expect_object(data, label, expected)
    for field in sorted(expected):
        _validate_matrix16(data[field], f"{label}.{field}")


def _validate_fbx_global_settings(data: Any) -> None:
    _expect_object(data, "rig.sourceFormat.fbx.globalSettings", _FBX_GLOBAL_SETTINGS_FIELDS)
    for field in (
        "UpAxis",
        "UpAxisSign",
        "FrontAxis",
        "FrontAxisSign",
        "CoordAxis",
        "CoordAxisSign",
        "TimeMode",
    ):
        _integer(data[field], f"rig.sourceFormat.fbx.globalSettings.{field}")
    for field in ("UnitScaleFactor", "OriginalUnitScaleFactor", "CustomFrameRate"):
        _finite(data[field], f"rig.sourceFormat.fbx.globalSettings.{field}")
    if float(data["UnitScaleFactor"]) <= 0 or float(data["OriginalUnitScaleFactor"]) <= 0:
        raise ValueError("FBX UnitScaleFactor and OriginalUnitScaleFactor must be positive")


def _validate_fbx_rig_metadata(data: Any, rig_bones: set[str]) -> None:
    expected_top = {"fbxVersion", "globalSettings", "bones"}
    _expect_object(data, "rig.sourceFormat.fbx", expected_top)
    version = _integer(data["fbxVersion"], "rig.sourceFormat.fbx.fbxVersion")
    if version < 7000:
        raise ValueError("rig.sourceFormat.fbx.fbxVersion must be an FBX 7.x+ integer")
    _validate_fbx_global_settings(data["globalSettings"])

    bones = data["bones"]
    if not isinstance(bones, dict) or set(bones) != rig_bones:
        missing = rig_bones - set(bones or {})
        extra = set(bones or {}) - rig_bones
        raise ValueError(f"rig.sourceFormat.fbx bone set mismatch; missing={sorted(missing)} extra={sorted(extra)}")
    for bone_name, payload in bones.items():
        _expect_object(payload, f"FBX metadata for {bone_name}", {"transformStack"}, {"encodingAdapter"})
        stack = payload["transformStack"]
        required_stack = set(_FBX_VECTOR_STACK_FIELDS) | {"RotationOrder", "RotationActive"}
        _expect_object(stack, f"FBX transformStack for {bone_name}", required_stack, {"InheritType"})
        for field in _FBX_VECTOR_STACK_FIELDS:
            vec(stack[field], 3, f"FBX {bone_name}.{field}")
        rotation_order = _integer(stack["RotationOrder"], f"FBX {bone_name}.RotationOrder")
        if not 0 <= rotation_order <= 6:
            raise ValueError(f"FBX {bone_name}.RotationOrder must be an integer in 0..6")
        _boolean(stack["RotationActive"], f"FBX {bone_name}.RotationActive")
        if "InheritType" in stack:
            _integer(stack["InheritType"], f"FBX {bone_name}.InheritType")
        if "encodingAdapter" in payload:
            _validate_fbx_encoding_adapter(payload["encodingAdapter"], f"FBX {bone_name}.encodingAdapter")


def _validate_fbx_animation_metadata(data: Any, expected_frame_count: int) -> None:
    expected = {"stack", "layer", "stackTiming", "sampling", "sampleKeyTimes"}
    if isinstance(data, dict) and "curves" in data:
        raise ValueError(
            "animation.sourceFormat.fbx.curves is forbidden: animation.frames is the sole motion authority"
        )
    _expect_object(data, "animation.sourceFormat.fbx", expected)
    _non_empty_string(data["stack"], "animation.sourceFormat.fbx.stack")
    _non_empty_string(data["layer"], "animation.sourceFormat.fbx.layer")
    if data["sampling"] != "all-integer-source-frames":
        raise ValueError("animation.sourceFormat.fbx.sampling must be 'all-integer-source-frames'")
    stack_timing = data["stackTiming"]
    _expect_object(stack_timing, "animation.sourceFormat.fbx.stackTiming", set(STACK_TIMING_FIELDS))
    for field in STACK_TIMING_FIELDS:
        _integer(stack_timing[field], f"animation.sourceFormat.fbx.stackTiming.{field}")
    sample_key_times = data["sampleKeyTimes"]
    if not isinstance(sample_key_times, list) or len(sample_key_times) != expected_frame_count:
        raise ValueError(
            "animation.sourceFormat.fbx.sampleKeyTimes must contain one integer KTime per source frame"
        )
    sample_key_times = [
        _integer(value, f"animation.sourceFormat.fbx.sampleKeyTimes[{index}]")
        for index, value in enumerate(sample_key_times)
    ]
    if any(right <= left for left, right in zip(sample_key_times, sample_key_times[1:])):
        raise ValueError("animation.sourceFormat.fbx.sampleKeyTimes must be strictly increasing")


def validate_rig_document(data: Any) -> dict:
    top_required = {
        "schema",
        "version",
        "id",
        "source",
        "coordinateSystem",
        "units",
        "restAuthority",
        "editGeometrySpace",
        "armatureObject",
        "bones",
    }
    _expect_object(data, "rig", top_required, {"sourceFormat"})
    version = _integer(data["version"], "rig.version")
    if data["schema"] != RIG_SCHEMA or version != VERSION:
        raise ValueError(f"unsupported rig schema/version: {data['schema']!r}/{data['version']!r}")
    validate_id(data["id"], "rig.id")
    source_format = _validate_source(data["source"], "rig.source", animation=False)

    coordinate_system = data["coordinateSystem"]
    _expect_object(
        coordinate_system,
        "rig.coordinateSystem",
        {"space", "handedness", "rightAxis", "forwardAxis", "upAxis"},
    )
    expected_coordinates = {
        "space": "Blender scene after source import",
        "handedness": "right-handed",
        "rightAxis": "+X",
        "forwardAxis": "-Y",
        "upAxis": "+Z",
    }
    for field, expected_value in expected_coordinates.items():
        if coordinate_system[field] != expected_value:
            raise ValueError(f"rig.coordinateSystem.{field} must be {expected_value!r}")

    units = data["units"]
    _expect_object(units, "rig.units", {"system", "metersPerBlenderUnit"})
    if not isinstance(units["system"], str):
        raise ValueError("rig.units.system must be a string")
    if _finite(units["metersPerBlenderUnit"], "rig.units.metersPerBlenderUnit") <= 0:
        raise ValueError("rig.units.metersPerBlenderUnit must be positive")

    if data["restAuthority"] != "editGeometry":
        raise ValueError("rig.restAuthority must be 'editGeometry'")
    if data["editGeometrySpace"] != "armature-local":
        raise ValueError("rig.editGeometrySpace must be 'armature-local'")

    armature_object = data["armatureObject"]
    _expect_object(armature_object, "rig.armatureObject", {"name", "dataName", "transform"})
    _non_empty_string(armature_object["name"], "rig.armatureObject.name")
    _non_empty_string(armature_object["dataName"], "rig.armatureObject.dataName")
    validate_trs(armature_object["transform"], "rig.armatureObject.transform")

    bones = data["bones"]
    if not isinstance(bones, list) or not bones:
        raise ValueError("rig.bones must be a non-empty list")
    names: set[str] = set()
    bone_required = {"name", "parent", "rest", "length", "editGeometry", "properties"}
    for index, bone in enumerate(bones):
        _expect_object(bone, f"rig.bones[{index}]", bone_required)
        name = _non_empty_string(bone["name"], f"rig.bones[{index}].name")
        if name in names:
            raise ValueError(f"duplicate bone name: {name}")
        names.add(name)
        parent = bone["parent"]
        if parent is not None and not isinstance(parent, str):
            raise ValueError(f"bone {name}.parent must be string or null")
        validate_trs(bone["rest"], f"bone {name}.rest")
        validate_edit_geometry(bone["editGeometry"], f"bone {name}.editGeometry")
        length = _finite(bone["length"], f"bone {name}.length")
        if length <= 0:
            raise ValueError(f"bone {name}.length must be positive")
        _validate_bone_properties(bone["properties"], f"bone {name}.properties")

    for bone in bones:
        parent = bone["parent"]
        if parent is not None and parent not in names:
            raise ValueError(f"bone {bone['name']} references missing parent {parent}")

    _validate_derived_rest_cache(bones)

    if source_format == "FBX":
        source_format_data = data.get("sourceFormat")
        _expect_object(source_format_data, "rig.sourceFormat", {"fbx"})
        _validate_fbx_rig_metadata(source_format_data["fbx"], names)
    elif "sourceFormat" in data:
        raise ValueError("non-FBX rig must not contain sourceFormat")
    return data


def validate_animation_document(data: Any, rig: dict) -> dict:
    top_required = {
        "schema",
        "version",
        "id",
        "rig",
        "source",
        "fps",
        "fpsNumerator",
        "fpsBase",
        "frameRange",
        "frameCount",
        "sampling",
        "transformSpace",
        "frames",
    }
    _expect_object(data, "animation", top_required, {"sourceFormat", "durationSeconds"})
    version = _integer(data["version"], "animation.version")
    if data["schema"] != ANIMATION_SCHEMA or version != VERSION:
        raise ValueError(f"unsupported animation schema/version: {data['schema']!r}/{data['version']!r}")
    validate_id(data["id"], "animation.id")

    rig_ref = data["rig"]
    _expect_object(rig_ref, "animation.rig", {"id"})
    if rig_ref["id"] != rig.get("id"):
        raise ValueError("animation.rig.id must match rig.id")

    source_format = _validate_source(data["source"], "animation.source", animation=True)
    if data["source"]["sha256"] != rig["source"]["sha256"]:
        raise ValueError("animation.source.sha256 must match rig.source.sha256")

    fps = _finite(data["fps"], "animation.fps")
    fps_numerator = _integer(data["fpsNumerator"], "animation.fpsNumerator")
    fps_base = _finite(data["fpsBase"], "animation.fpsBase")
    if fps <= 0 or fps_numerator <= 0 or fps_base <= 0:
        raise ValueError("animation FPS values must be positive")
    if abs(fps - fps_numerator / fps_base) > 1e-9:
        raise ValueError("animation.fps contradicts fpsNumerator/fpsBase")

    frame_range = data["frameRange"]
    if not isinstance(frame_range, list) or len(frame_range) != 2:
        raise ValueError("animation.frameRange must be [integerStart, integerEnd]")
    start = _integer(frame_range[0], "animation.frameRange[0]")
    end = _integer(frame_range[1], "animation.frameRange[1]")
    if end < start:
        raise ValueError("animation.frameRange end must be >= start")

    if "durationSeconds" in data:
        duration_seconds = _finite(data["durationSeconds"], "animation.durationSeconds")
        if duration_seconds < 0.0:
            raise ValueError("animation.durationSeconds must be non-negative")
        expected_duration = (end - start) / fps
        if abs(duration_seconds - expected_duration) > DURATION_TOLERANCE_SECONDS:
            raise ValueError(
                "animation.durationSeconds contradicts frameRange/fps: "
                f"durationSeconds={duration_seconds:.12g} expected={expected_duration:.12g}"
            )

    sampling = data["sampling"]
    _expect_object(
        sampling,
        "animation.sampling",
        {"policy", "step", "continuousSubframeBehaviorPreserved"},
    )
    if sampling["policy"] != "all-integer-source-frames-inclusive":
        raise ValueError("animation.sampling.policy must be 'all-integer-source-frames-inclusive'")
    sampling_step = _integer(sampling["step"], "animation.sampling.step")
    if sampling_step != 1:
        raise ValueError("animation.sampling.step must be 1")
    continuous_preserved = _boolean(
        sampling["continuousSubframeBehaviorPreserved"],
        "animation.sampling.continuousSubframeBehaviorPreserved",
    )
    if continuous_preserved:
        raise ValueError("animation.sampling.continuousSubframeBehaviorPreserved must be false")

    transform_space = data["transformSpace"]
    _expect_object(transform_space, "animation.transformSpace", {"name", "description"})
    if transform_space["name"] != "blender-pose-matrix-basis":
        raise ValueError("animation.transformSpace.name must be 'blender-pose-matrix-basis'")
    expected_description = (
        "Per-bone PoseBone.matrix_basis: pose-local delta relative to the bone rest basis, "
        "serialized as TRS."
    )
    if transform_space["description"] != expected_description:
        raise ValueError("animation.transformSpace.description does not match the canonical contract")

    frames = data["frames"]
    if not isinstance(frames, list) or not frames:
        raise ValueError("animation.frames must be non-empty")
    expected_frames = list(range(start, end + 1))
    actual_frames: list[int] = []
    for index, entry in enumerate(frames):
        _expect_object(entry, f"animation.frames[{index}]", {"frame", "bones"})
        actual_frames.append(_integer(entry["frame"], f"animation.frames[{index}].frame"))
    if actual_frames != expected_frames:
        raise ValueError(
            f"animation.frames must be ordered and contiguous: expected {expected_frames[0]}..{expected_frames[-1]}"
        )
    frame_count = _integer(data["frameCount"], "animation.frameCount")
    if frame_count != len(expected_frames):
        raise ValueError("animation.frameCount contradicts frameRange")

    rig_bones = {bone["name"] for bone in rig["bones"]}
    for entry in frames:
        bones = entry["bones"]
        if not isinstance(bones, dict) or set(bones) != rig_bones:
            missing = rig_bones - set(bones or {})
            extra = set(bones or {}) - rig_bones
            raise ValueError(f"frame {entry['frame']} bone set mismatch; missing={sorted(missing)} extra={sorted(extra)}")
        for bone_name, transform in bones.items():
            validate_trs(transform, f"frame {entry['frame']} bone {bone_name}")

    if source_format == "FBX":
        source_format_data = data.get("sourceFormat")
        _expect_object(source_format_data, "animation.sourceFormat", {"fbx"})
        _validate_fbx_animation_metadata(source_format_data["fbx"], len(expected_frames))
    elif "sourceFormat" in data:
        raise ValueError("non-FBX animation must not contain sourceFormat")
    return data


def canonical_json_text(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False, separators=(",", ": ")) + "\n"


def write_canonical_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json_text(data), encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
