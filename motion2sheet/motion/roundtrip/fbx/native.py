from __future__ import annotations

import array
import math
from pathlib import Path
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


def extract_fbx_authority(
    path: Path, bone_names: list[str], expected_frame_count: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    root, version = parse_fbx.parse(str(path), use_namedtuple=True)
    table = _node_table(root)
    forward, _reverse = _connection_maps(root)
    requested = set(bone_names)

    models_by_name = {
        _name(elem): elem
        for elem in table.values()
        if elem.id == b"Model" and _name(elem) in requested
    }
    if set(models_by_name) != requested:
        missing = sorted(requested - set(models_by_name))
        raise RuntimeError(f"FBX source-format extraction cannot resolve rig bone Models: {missing}")

    bone_model_ids = {name: int(model.props[0]) for name, model in models_by_name.items()}
    model_name_by_id = {model_id: name for name, model_id in bone_model_ids.items()}

    stacks = [elem for elem in table.values() if elem.id == b"AnimationStack" and elem.props[2] == b""]
    layers = [elem for elem in table.values() if elem.id == b"AnimationLayer" and elem.props[2] == b""]
    if len(stacks) != 1 or len(layers) != 1:
        raise RuntimeError(
            "POC v1 requires exactly one FBX AnimationStack and one AnimationLayer; "
            f"found stacks={len(stacks)} layers={len(layers)}"
        )

    layer_id = int(layers[0].props[0])
    stack_id = int(stacks[0].props[0])
    layer_to_stack = [
        link
        for link in forward.get(layer_id, ())
        if link.props[0] == b"OO" and int(link.props[2]) == stack_id
    ]
    if not layer_to_stack:
        raise RuntimeError("FBX AnimationLayer is not connected to the single AnimationStack")

    curve_node_targets: dict[int, tuple[str, str]] = {}
    for elem_id, elem in table.items():
        if elem.id != b"AnimationCurveNode" or elem.props[2] != b"":
            continue
        model_links = [
            link
            for link in forward.get(elem_id, ())
            if link.props[0] == b"OP"
            and len(link.props) >= 4
            and int(link.props[2]) in model_name_by_id
            and link.props[3] in ANIM_PROPERTIES
        ]
        if not model_links:
            continue
        if len(model_links) != 1:
            raise RuntimeError(f"FBX curve node {_name(elem)!r} targets multiple rig transform properties")
        link = model_links[0]
        curve_node_targets[elem_id] = (
            model_name_by_id[int(link.props[2])],
            ANIM_PROPERTIES[link.props[3]],
        )

    curves: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for curve_id, curve in table.items():
        if curve.id != b"AnimationCurve" or curve.props[2] != b"":
            continue
        links = [
            link
            for link in forward.get(curve_id, ())
            if link.props[0] == b"OP"
            and len(link.props) >= 4
            and int(link.props[2]) in curve_node_targets
            and link.props[3] in AXIS_BY_CONNECTION
        ]
        if not links:
            continue
        if len(links) != 1:
            raise RuntimeError(f"FBX animation curve {_name(curve)!r} maps to multiple rig channels")
        link = links[0]
        bone, prop = curve_node_targets[int(link.props[2])]
        axis = AXIS_BY_CONNECTION[link.props[3]]
        key = (bone, prop, axis)
        if key in seen_keys:
            raise RuntimeError(f"POC v1 does not support multiple FBX curves for {bone} {prop}.{axis}")
        seen_keys.add(key)
        times, values = _curve_arrays(curve)
        curves.append(
            {
                "bone": bone,
                "property": prop,
                "axis": axis,
                "keyTimes": times,
                "keyValues": values,
            }
        )

    if not curves:
        raise RuntimeError("No FBX transform animation curves were resolved for rig bones")

    # POC v1 authority is the state at every integer source frame, not the
    # source FCurve sparsity/tangent representation. Mixamo commonly stores
    # constant channels with a single key while animated channels contain one
    # key per source frame. Resolve one canonical FBX KTime timeline from the
    # animated channels, then expand constant channels onto that same timeline.
    timelines = {
        tuple(curve["keyTimes"])
        for curve in curves
        if len(curve["keyTimes"]) > 1
    }
    if len(timelines) != 1:
        raise RuntimeError(
            "POC v1 requires all multi-key FBX transform curves to share one "
            f"integer-frame timeline; found {len(timelines)} timelines"
        )
    sample_key_times = list(next(iter(timelines)))
    if len(sample_key_times) != expected_frame_count:
        raise RuntimeError(
            "FBX source timeline does not match Blender integer-frame contract: "
            f"FBX samples={len(sample_key_times)} expectedFrames={expected_frame_count}"
        )
    normalized_curves: list[dict[str, Any]] = []
    for curve in curves:
        times = curve["keyTimes"]
        values = curve["keyValues"]
        if times == sample_key_times:
            normalized_values = values
        elif len(times) == 1:
            normalized_values = [values[0]] * len(sample_key_times)
        else:
            raise RuntimeError(
                "POC v1 cannot normalize sparse/nonuniform FBX curve "
                f"{curve['bone']} {curve['property']}.{curve['axis']}; "
                f"keys={len(times)} expected={len(sample_key_times)}"
            )
        normalized_curves.append(
            {
                **curve,
                "keyTimes": sample_key_times,
                "keyValues": normalized_values,
            }
        )
    curves = normalized_curves

    # Blender's FBX exporter bakes T/R/S curves for every bone. If we leave a
    # generated curve unpatched, that container-only channel becomes a second
    # animation authority and can extend the timeline or override source Lcl
    # defaults. Make the JSON FBX adapter complete at the POC sampling level:
    # every rig bone owns all 9 scalar T/R/S channels on every integer frame.
    bone_stacks = {
        name: _model_transform_stack(models_by_name[name])
        for name in sorted(models_by_name)
    }
    curve_map = {
        (curve["bone"], curve["property"], curve["axis"]): curve
        for curve in curves
    }
    stack_field_by_property = {
        "translation": "Lcl Translation",
        "rotation": "Lcl Rotation",
        "scale": "Lcl Scaling",
    }
    axis_names = ("x", "y", "z")
    for bone_name, stack in bone_stacks.items():
        for property_name, stack_field in stack_field_by_property.items():
            default_values = stack[stack_field]
            for axis_index, axis_name in enumerate(axis_names):
                key = (bone_name, property_name, axis_name)
                if key in curve_map:
                    continue
                value = float(default_values[axis_index])
                curve = {
                    "bone": bone_name,
                    "property": property_name,
                    "axis": axis_name,
                    "keyTimes": sample_key_times,
                    "keyValues": [value] * len(sample_key_times),
                }
                curves.append(curve)
                curve_map[key] = curve

    rig_authority = {
        "fbxVersion": int(version),
        "globalSettings": _global_settings(root),
        "bones": {
            name: {"transformStack": bone_stacks[name]}
            for name in sorted(bone_stacks)
        },
    }
    animation_authority = {
        "stack": _name(stacks[0]),
        "layer": _name(layers[0]),
        "sampling": "all-integer-source-frames",
        "sampleKeyTimes": sample_key_times,
        "curves": sorted(curves, key=lambda item: (item["bone"], item["property"], item["axis"])),
    }
    return rig_authority, animation_authority


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


def _replace_curve_arrays(curve, times: list[int], values: list[float]) -> None:
    key_time = _find_first(curve, b"KeyTime")
    key_value = _find_first(curve, b"KeyValueFloat")
    if key_time is None or key_value is None or not key_time.props or not key_value.props:
        raise RuntimeError(f"Generated FBX curve {_name(curve)!r} lacks key arrays")
    existing_times = key_time.props[0]
    existing_values = key_value.props[0]
    if len(existing_times) != len(times) or len(existing_values) != len(values):
        raise RuntimeError(
            f"Generated/source FBX key count mismatch for {_name(curve)!r}: "
            f"target={len(existing_times)} source={len(times)}"
        )
    key_time.props[0] = array.array(existing_times.typecode, times)
    key_value.props[0] = array.array(existing_values.typecode, values)


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


def patch_generated_fbx(
    generated_path: Path,
    output_path: Path,
    rig_fbx: dict[str, Any],
    animation_fbx: dict[str, Any],
) -> None:
    root, version = parse_fbx.parse(str(generated_path), use_namedtuple=True)
    models = {_name(elem): elem for elem in _objects(root) if elem.id == b"Model"}
    expected_bones = set(rig_fbx["bones"])
    missing = sorted(expected_bones - set(models))
    if missing:
        raise RuntimeError(f"Generated FBX is missing rig bone Models required by JSON: {missing}")
    for bone_name, payload in rig_fbx["bones"].items():
        _patch_model_transform(models[bone_name], payload["transformStack"])

    target_curves = _target_curve_map(root)
    for curve in animation_fbx["curves"]:
        key = (curve["bone"], curve["property"], curve["axis"])
        target = target_curves.get(key)
        if target is None:
            raise RuntimeError(f"Generated FBX is missing animation curve required by JSON: {key}")
        _replace_curve_arrays(target, curve["keyTimes"], curve["keyValues"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    encode_bin.write(str(output_path), _clone_for_encoder(root), version)
