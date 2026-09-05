from __future__ import annotations

import array
import math
from typing import Any

from io_scene_fbx import encode_bin, parse_fbx
from io_scene_fbx.parse_fbx import data_types

TRANSFORM_PROPERTIES = (
    "Lcl Translation",
    "Lcl Rotation",
    "Lcl Scaling",
    "PreRotation",
    "PostRotation",
    "RotationOffset",
    "RotationPivot",
    "ScalingOffset",
    "ScalingPivot",
    "RotationOrder",
    "RotationActive",
    "InheritType",
)
ANIM_PROPERTIES = {
    b"Lcl Translation": "translation",
    b"Lcl Rotation": "rotation",
    b"Lcl Scaling": "scale",
}
AXIS_BY_CONNECTION = {b"d|X": "x", b"d|Y": "y", b"d|Z": "z"}
STACK_TIMING_FIELDS = ("LocalStart", "LocalStop", "ReferenceStart", "ReferenceStop")


def _fbx_timebase(root, version: int) -> dict[str, int | None]:
    from motion2sheet.motion.roundtrip.native_timing import resolve_fbx_ticks_per_second

    header = _find_first(root, b"FBXHeaderExtension")
    header_version_elem = _find_first(header, b"FBXHeaderVersion") if header is not None else None
    header_version = int(header_version_elem.props[0]) if header_version_elem is not None and header_version_elem.props else 0
    other_flags = _find_first(header, b"OtherFlags") if header is not None else None
    definition_elem = _find_first(other_flags, b"TCDefinition") if other_flags is not None else None
    definition = int(definition_elem.props[0]) if definition_elem is not None and definition_elem.props else None
    return {
        "fbxHeaderVersion": header_version,
        "timecodeDefinition": definition,
        "ticksPerSecond": resolve_fbx_ticks_per_second(
            int(version),
            header_version=header_version,
            timecode_definition=definition,
        ),
    }


def _find_first(elem, elem_id: bytes):
    for child in elem.elems:
        if child.id == elem_id:
            return child
    return None


def _name(elem) -> str:
    raw = elem.props[-2]
    if isinstance(raw, bytes):
        raw = raw.split(b"\x00\x01", 1)[0].decode("utf-8", "replace")
    prefix = {
        b"Model": "Model::",
        b"AnimationStack": "AnimStack::",
        b"AnimationLayer": "AnimLayer::",
    }.get(elem.id)
    if prefix and raw.startswith(prefix):
        raw = raw[len(prefix) :]
    return str(raw)


def _json_value(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, array.array):
        return list(value)
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, (int, float, bool, str)) or value is None:
        return value
    return list(value)


def _properties70(elem) -> dict[str, Any]:
    props70 = _find_first(elem, b"Properties70")
    result: dict[str, Any] = {}
    if props70 is None:
        return result
    for prop in props70.elems:
        if prop.id != b"P" or len(prop.props) < 5:
            continue
        name = prop.props[0].decode("utf-8", "replace") if isinstance(prop.props[0], bytes) else str(prop.props[0])
        values = [_json_value(value) for value in prop.props[4:]]
        result[name] = values[0] if len(values) == 1 else values
    return result


def _connections(root) -> list:
    connections = _find_first(root, b"Connections")
    return [] if connections is None else list(connections.elems)


def _objects(root) -> list:
    objects = _find_first(root, b"Objects")
    return [] if objects is None else list(objects.elems)


def _connection_maps(root):
    forward: dict[int, list] = {}
    reverse: dict[int, list] = {}
    for link in _connections(root):
        if len(link.props) < 3 or link.props_type[1:3] != b"LL":
            continue
        src, dst = int(link.props[1]), int(link.props[2])
        forward.setdefault(src, []).append(link)
        reverse.setdefault(dst, []).append(link)
    return forward, reverse


def _node_table(root) -> dict[int, Any]:
    return {
        int(elem.props[0]): elem
        for elem in _objects(root)
        if len(elem.props) >= 3 and elem.props_type[:3] == b"LSS"
    }


def _global_settings(root) -> dict[str, Any]:
    settings = _find_first(root, b"GlobalSettings")
    props = _properties70(settings) if settings is not None else {}
    keys = (
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
    )
    return {key: props[key] for key in keys if key in props}


def _model_transform_stack(model) -> dict[str, Any]:
    props = _properties70(model)
    result = {key: props[key] for key in TRANSFORM_PROPERTIES if key in props}
    result.setdefault("Lcl Translation", [0.0, 0.0, 0.0])
    result.setdefault("Lcl Rotation", [0.0, 0.0, 0.0])
    result.setdefault("Lcl Scaling", [1.0, 1.0, 1.0])
    result.setdefault("PreRotation", [0.0, 0.0, 0.0])
    result.setdefault("PostRotation", [0.0, 0.0, 0.0])
    result.setdefault("RotationOffset", [0.0, 0.0, 0.0])
    result.setdefault("RotationPivot", [0.0, 0.0, 0.0])
    result.setdefault("ScalingOffset", [0.0, 0.0, 0.0])
    result.setdefault("ScalingPivot", [0.0, 0.0, 0.0])
    result["RotationOrder"] = int(result.get("RotationOrder", 0))
    rotation_active_default = bool(
        any(abs(float(value)) > 1e-12 for value in result["PreRotation"])
        or any(abs(float(value)) > 1e-12 for value in result["PostRotation"])
    )
    result["RotationActive"] = bool(result.get("RotationActive", rotation_active_default))
    if "InheritType" in result:
        result["InheritType"] = int(result["InheritType"])
    return result


def _curve_arrays(curve) -> tuple[list[int], list[float]]:
    times_elem = _find_first(curve, b"KeyTime")
    values_elem = _find_first(curve, b"KeyValueFloat")
    if times_elem is None or values_elem is None or not times_elem.props or not values_elem.props:
        raise RuntimeError(f"FBX animation curve {_name(curve)!r} is missing KeyTime/KeyValueFloat")
    times = [int(value) for value in times_elem.props[0]]
    values = [float(value) for value in values_elem.props[0]]
    if len(times) != len(values) or not times:
        raise RuntimeError(f"FBX animation curve {_name(curve)!r} has invalid key arrays")
    if any(right <= left for left, right in zip(times, times[1:])):
        raise RuntimeError(f"FBX animation curve {_name(curve)!r} has non-increasing KeyTime values")
    if not all(math.isfinite(value) for value in values):
        raise RuntimeError(f"FBX animation curve {_name(curve)!r} contains non-finite values")
    return times, values


def _parsed_property(props70, name: str):
    name_bytes = name.encode("utf-8")
    for prop in props70.elems:
        if prop.id == b"P" and prop.props and prop.props[0] == name_bytes:
            return prop
    return None


_VECTOR_PROP_TYPES = {
    "Lcl Translation": (b"Lcl Translation", b"Lcl Translation"),
    "Lcl Rotation": (b"Lcl Rotation", b"Lcl Rotation"),
    "Lcl Scaling": (b"Lcl Scaling", b"Lcl Scaling"),
    "PreRotation": (b"Vector3D", b"Vector"),
    "PostRotation": (b"Vector3D", b"Vector"),
    "RotationOffset": (b"Vector3D", b"Vector"),
    "RotationPivot": (b"Vector3D", b"Vector"),
    "ScalingOffset": (b"Vector3D", b"Vector"),
    "ScalingPivot": (b"Vector3D", b"Vector"),
}


def _set_vector_property(props70, name: str, values: list[float]) -> None:
    existing = _parsed_property(props70, name)
    if existing is not None:
        if len(existing.props) < 7:
            raise RuntimeError(f"Generated FBX property {name!r} has unexpected encoding")
        existing.props[-3:] = [float(value) for value in values]
        return
    type_name, subtype = _VECTOR_PROP_TYPES[name]
    props70.elems.append(
        parse_fbx.FBXElem(
            b"P",
            [name.encode(), type_name, subtype, b"", *[float(value) for value in values]],
            bytearray(
                [
                    data_types.STRING,
                    data_types.STRING,
                    data_types.STRING,
                    data_types.STRING,
                    data_types.FLOAT64,
                    data_types.FLOAT64,
                    data_types.FLOAT64,
                ]
            ),
            [],
        )
    )


def _set_scalar_property(props70, name: str, value: Any) -> None:
    existing = _parsed_property(props70, name)
    if existing is not None:
        if len(existing.props) < 5:
            raise RuntimeError(f"Generated FBX property {name!r} has unexpected encoding")
        existing.props[-1] = int(bool(value)) if name == "RotationActive" else int(value)
        return
    prop_type = b"bool" if name == "RotationActive" else b"enum"
    props70.elems.append(
        parse_fbx.FBXElem(
            b"P",
            [name.encode(), prop_type, b"", b"", int(bool(value)) if name == "RotationActive" else int(value)],
            bytearray(
                [
                    data_types.STRING,
                    data_types.STRING,
                    data_types.STRING,
                    data_types.STRING,
                    data_types.INT32,
                ]
            ),
            [],
        )
    )


def _patch_model_transform(model, transform_stack: dict[str, Any]) -> None:
    props70 = _find_first(model, b"Properties70")
    if props70 is None:
        raise RuntimeError(f"Generated FBX Model {_name(model)!r} lacks Properties70")
    for name in _VECTOR_PROP_TYPES:
        if name in transform_stack:
            _set_vector_property(props70, name, transform_stack[name])
    for name in ("RotationOrder", "RotationActive", "InheritType"):
        if name in transform_stack:
            _set_scalar_property(props70, name, transform_stack[name])


def _patch_stack_timing(root, stack_timing: dict[str, int]) -> None:
    table = _node_table(root)
    stacks = [elem for elem in table.values() if elem.id == b"AnimationStack"]
    if len(stacks) != 1:
        raise RuntimeError(
            f"Generated FBX must contain exactly one AnimationStack; found {len(stacks)}"
        )
    props70 = _find_first(stacks[0], b"Properties70")
    if props70 is None:
        raise RuntimeError("Generated FBX AnimationStack lacks Properties70")
    for field in STACK_TIMING_FIELDS:
        prop = _parsed_property(props70, field)
        if prop is None or len(prop.props) < 5:
            raise RuntimeError(f"Generated FBX AnimationStack lacks {field}")
        prop.props[-1] = int(stack_timing[field])


def _set_int32_child(parent, child_id: bytes, value: int):
    child = _find_first(parent, child_id)
    if child is None:
        child = parse_fbx.FBXElem(
            child_id,
            [int(value)],
            bytearray([data_types.INT32]),
            [],
        )
        parent.elems.append(child)
    else:
        if len(child.props) != 1:
            raise RuntimeError(f"FBX {child_id.decode()} has unexpected encoding")
        child.props[0] = int(value)
    return child


def _patch_timebase(root, fbx_version: int, ticks_per_second: int) -> None:
    from motion2sheet.motion.roundtrip.native_timing import FBX_KTIME_V7, FBX_KTIME_V8

    if ticks_per_second == FBX_KTIME_V8 and fbx_version < 7700:
        raise RuntimeError("FBX v8 KTime cannot be encoded into an FBX version older than 7700")
    if ticks_per_second not in {FBX_KTIME_V7, FBX_KTIME_V8}:
        raise RuntimeError(f"Unsupported FBX KTime ticks-per-second value: {ticks_per_second}")
    if fbx_version < 7700 and ticks_per_second == FBX_KTIME_V7:
        return

    header = _find_first(root, b"FBXHeaderExtension")
    if header is None:
        raise RuntimeError("Generated FBX lacks FBXHeaderExtension")
    header_version_elem = _find_first(header, b"FBXHeaderVersion")
    header_version = int(header_version_elem.props[0]) if header_version_elem is not None and header_version_elem.props else 0
    _set_int32_child(header, b"FBXHeaderVersion", max(header_version, 1004))
    other_flags = _find_first(header, b"OtherFlags")
    if other_flags is None:
        other_flags = parse_fbx.FBXElem(b"OtherFlags", [], bytearray(), [])
        header.elems.append(other_flags)
    definition = 127 if ticks_per_second == FBX_KTIME_V7 else 0
    _set_int32_child(other_flags, b"TCDefinition", definition)


def _target_curve_map(root) -> dict[tuple[str, str, str], Any]:
    table = _node_table(root)
    forward, _reverse = _connection_maps(root)
    model_names = {elem_id: _name(elem) for elem_id, elem in table.items() if elem.id == b"Model"}
    curve_node_targets: dict[int, tuple[str, str]] = {}
    for elem_id, elem in table.items():
        if elem.id != b"AnimationCurveNode":
            continue
        links = [
            link
            for link in forward.get(elem_id, ())
            if link.props[0] == b"OP"
            and len(link.props) >= 4
            and int(link.props[2]) in model_names
            and link.props[3] in ANIM_PROPERTIES
        ]
        if len(links) == 1:
            link = links[0]
            curve_node_targets[elem_id] = (
                model_names[int(link.props[2])],
                ANIM_PROPERTIES[link.props[3]],
            )
    result: dict[tuple[str, str, str], Any] = {}
    for elem_id, elem in table.items():
        if elem.id != b"AnimationCurve":
            continue
        links = [
            link
            for link in forward.get(elem_id, ())
            if link.props[0] == b"OP"
            and len(link.props) >= 4
            and int(link.props[2]) in curve_node_targets
            and link.props[3] in AXIS_BY_CONNECTION
        ]
        if len(links) != 1:
            continue
        link = links[0]
        bone, prop = curve_node_targets[int(link.props[2])]
        key = (bone, prop, AXIS_BY_CONNECTION[link.props[3]])
        if key in result:
            raise RuntimeError(f"Generated FBX contains duplicate curve mapping for {key}")
        result[key] = elem
    return result


def _clone_for_encoder(elem):
    cloned = encode_bin.FBXElem(elem.id)
    for value, prop_type in zip(elem.props, elem.props_type):
        if prop_type == data_types.BOOL:
            cloned.add_bool(bool(value))
        elif prop_type == data_types.CHAR:
            cloned.add_char(value)
        elif prop_type == data_types.INT8:
            cloned.add_int8(int(value))
        elif prop_type == data_types.INT16:
            cloned.add_int16(int(value))
        elif prop_type == data_types.INT32:
            cloned.add_int32(int(value))
        elif prop_type == data_types.INT64:
            cloned.add_int64(int(value))
        elif prop_type == data_types.FLOAT32:
            cloned.add_float32(float(value))
        elif prop_type == data_types.FLOAT64:
            cloned.add_float64(float(value))
        elif prop_type == data_types.BYTES:
            cloned.add_bytes(value)
        elif prop_type == data_types.STRING:
            cloned.add_string(value)
        elif prop_type == data_types.INT32_ARRAY:
            cloned.add_int32_array(value)
        elif prop_type == data_types.INT64_ARRAY:
            cloned.add_int64_array(value)
        elif prop_type == data_types.FLOAT32_ARRAY:
            cloned.add_float32_array(value)
        elif prop_type == data_types.FLOAT64_ARRAY:
            cloned.add_float64_array(value)
        elif prop_type == data_types.BOOL_ARRAY:
            cloned.add_bool_array(value)
        elif prop_type == data_types.BYTE_ARRAY:
            cloned.add_byte_array(value)
        else:
            raise RuntimeError(f"Unsupported FBX property type byte: {prop_type!r}")
    cloned.elems = [_clone_for_encoder(child) for child in elem.elems]
    return cloned
