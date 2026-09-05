from __future__ import annotations

from pathlib import Path
from typing import Any

from io_scene_fbx import parse_fbx

from . import native


def extract_fbx_metadata_and_diagnostics(
    path: Path,
    bone_names: list[str],
    expected_frame_count: int,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Extract static FBX encoding metadata plus a diagnostic-only copy of source curves.

    The returned curve list is deliberately separate from canonical rig/animation metadata.
    Reconstruction must derive its Lcl T/R/S samples from animation.frames instead.
    """

    root, version = parse_fbx.parse(str(path), use_namedtuple=True)
    timebase = native._fbx_timebase(root, int(version))
    table = native._node_table(root)
    forward, _reverse = native._connection_maps(root)
    requested = set(bone_names)

    models_by_name = {
        native._name(elem): elem
        for elem in table.values()
        if elem.id == b"Model" and native._name(elem) in requested
    }
    if set(models_by_name) != requested:
        missing = sorted(requested - set(models_by_name))
        raise RuntimeError(f"FBX metadata extraction cannot resolve rig bone Models: {missing}")

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
    if not any(
        link.props[0] == b"OO" and int(link.props[2]) == stack_id
        for link in forward.get(layer_id, ())
    ):
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
            and link.props[3] in native.ANIM_PROPERTIES
        ]
        if not model_links:
            continue
        if len(model_links) != 1:
            raise RuntimeError(f"FBX curve node {native._name(elem)!r} targets multiple rig transform properties")
        link = model_links[0]
        curve_node_targets[elem_id] = (
            model_name_by_id[int(link.props[2])],
            native.ANIM_PROPERTIES[link.props[3]],
        )

    source_curves: list[dict[str, Any]] = []
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
            and link.props[3] in native.AXIS_BY_CONNECTION
        ]
        if not links:
            continue
        if len(links) != 1:
            raise RuntimeError(f"FBX animation curve {native._name(curve)!r} maps to multiple rig channels")
        link = links[0]
        bone, prop = curve_node_targets[int(link.props[2])]
        axis = native.AXIS_BY_CONNECTION[link.props[3]]
        key = (bone, prop, axis)
        if key in seen_keys:
            raise RuntimeError(f"POC v1 does not support multiple FBX curves for {bone} {prop}.{axis}")
        seen_keys.add(key)
        times, values = native._curve_arrays(curve)
        source_curves.append(
            {
                "bone": bone,
                "property": prop,
                "axis": axis,
                "keyTimes": times,
                "keyValues": values,
            }
        )

    if not source_curves:
        raise RuntimeError("No FBX transform animation curves were resolved for rig bones")

    timelines = {
        tuple(curve["keyTimes"])
        for curve in source_curves
        if len(curve["keyTimes"]) > 1
    }
    if len(timelines) != 1:
        raise RuntimeError(
            "POC v1 requires all multi-key FBX transform curves to share one integer-frame timeline; "
            f"found {len(timelines)} timelines"
        )
    sample_key_times = list(next(iter(timelines)))
    if len(sample_key_times) != expected_frame_count:
        raise RuntimeError(
            "FBX source timeline does not match Blender integer-frame contract: "
            f"FBX samples={len(sample_key_times)} expectedFrames={expected_frame_count}"
        )

    normalized_curves: list[dict[str, Any]] = []
    for curve in source_curves:
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
    source_curves = normalized_curves

    bone_stacks = {
        name: native._model_transform_stack(models_by_name[name])
        for name in sorted(models_by_name)
    }
    curve_map = {
        (curve["bone"], curve["property"], curve["axis"]): curve
        for curve in source_curves
    }
    stack_field_by_property = {
        "translation": "Lcl Translation",
        "rotation": "Lcl Rotation",
        "scale": "Lcl Scaling",
    }
    for bone_name, stack in bone_stacks.items():
        for property_name, stack_field in stack_field_by_property.items():
            defaults = stack[stack_field]
            for axis_index, axis_name in enumerate(("x", "y", "z")):
                key = (bone_name, property_name, axis_name)
                if key in curve_map:
                    continue
                curve = {
                    "bone": bone_name,
                    "property": property_name,
                    "axis": axis_name,
                    "keyTimes": sample_key_times,
                    "keyValues": [float(defaults[axis_index])] * len(sample_key_times),
                }
                source_curves.append(curve)
                curve_map[key] = curve

    rig_metadata = {
        "fbxVersion": int(version),
        "globalSettings": native._global_settings(root),
        "bones": {
            name: {"transformStack": bone_stacks[name]}
            for name in sorted(bone_stacks)
        },
    }

    stack_properties = native._properties70(stacks[0])
    effective_local_start = int(stack_properties.get("LocalStart", sample_key_times[0]))
    effective_local_stop = int(stack_properties.get("LocalStop", sample_key_times[-1]))
    stack_timing = {
        "LocalStart": effective_local_start,
        "LocalStop": effective_local_stop,
        "ReferenceStart": int(stack_properties.get("ReferenceStart", effective_local_start)),
        "ReferenceStop": int(stack_properties.get("ReferenceStop", effective_local_stop)),
    }
    animation_metadata = {
        "stack": native._name(stacks[0]),
        "layer": native._name(layers[0]),
        "stackTiming": stack_timing,
        "sampling": "all-integer-source-frames",
        "sampleKeyTimes": sample_key_times,
        "ktimeTicksPerSecond": timebase["ticksPerSecond"],
    }
    return (
        rig_metadata,
        animation_metadata,
        sorted(source_curves, key=lambda item: (item["bone"], item["property"], item["axis"])),
    )
