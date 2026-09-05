from __future__ import annotations

import array
import math
from pathlib import Path
from typing import Any

from io_scene_fbx import encode_bin, parse_fbx
from mathutils import Euler, Matrix, Vector

from motion2sheet.motion.roundtrip.blender_common import matrix_residual, trs_to_matrix

from . import native

ROTATION_ORDERS = {
    0: "XYZ",
    1: "XZY",
    2: "YZX",
    3: "YXZ",
    4: "ZXY",
    5: "ZYX",
    6: "XYZ",  # Blender's FBX importer fallback for eSphericXYZ.
}
ENCODE_RESIDUAL_TOLERANCE = 2e-5
ORTHOGONAL_TOLERANCE = 2e-5
CONTAINER_CONSTANT_TOLERANCE = 1e-7


def _matrix(values: list[float]) -> Matrix:
    if len(values) != 16:
        raise RuntimeError(f"Expected 16 matrix values, got {len(values)}")
    return Matrix((values[0:4], values[4:8], values[8:12], values[12:16]))


def _translation(values) -> Matrix:
    return Matrix.Translation(Vector(tuple(float(value) for value in values)))


def _rotation(values, order: str = "XYZ") -> Matrix:
    return Euler(tuple(math.radians(float(value)) for value in values), order).to_matrix().to_4x4()


def _scale(values) -> Matrix:
    matrix = Matrix.Identity(4)
    for index, value in enumerate(values):
        matrix[index][index] = float(value)
    return matrix


def _max_identity_3x3_error(matrix: Matrix) -> float:
    return max(
        abs(float(matrix[row][column]) - (1.0 if row == column else 0.0))
        for row in range(3)
        for column in range(3)
    )


def _orthogonal_error(matrix3) -> float:
    columns = [matrix3.col[index].copy() for index in range(3)]
    for column in columns:
        if column.length <= 1e-12:
            return float("inf")
        column.normalize()
    return max(abs(float(columns[left].dot(columns[right]))) for left in range(3) for right in range(left + 1, 3))


def _effective_rotation_stack(stack: dict[str, Any]) -> tuple[Matrix, Matrix, str]:
    if not bool(stack.get("RotationActive", False)):
        return Matrix.Identity(4), Matrix.Identity(4), "XYZ"
    order_value = int(stack.get("RotationOrder", 0))
    if order_value not in ROTATION_ORDERS:
        raise RuntimeError(f"Unsupported FBX RotationOrder {order_value}")
    return _rotation(stack["PreRotation"]), _rotation(stack["PostRotation"]), ROTATION_ORDERS[order_value]


def _derive_lcl_trs(
    target_basis: Matrix,
    stack: dict[str, Any],
    adapter: dict[str, Any],
    previous_euler: Euler | None,
    *,
    bone_name: str,
    frame: int,
) -> tuple[list[float], list[float], list[float], Euler]:
    pre_adapter = _matrix(adapter["preMatrix"])
    post_adapter = _matrix(adapter["postMatrix"])
    geometry = _matrix(adapter["geometryMatrix"])
    rotation_alt = _matrix(adapter["rotationAltMatrix"])

    base_target = (
        pre_adapter.inverted_safe()
        @ target_basis
        @ post_adapter.inverted_safe()
        @ geometry.inverted_safe()
    )

    pre_rotation, post_rotation, rotation_order = _effective_rotation_stack(stack)
    linear = pre_rotation.to_3x3().inverted_safe() @ base_target.to_3x3()
    if _orthogonal_error(linear) > ORTHOGONAL_TOLERANCE:
        raise RuntimeError(
            f"FBX inverse encoder cannot represent {bone_name} frame {frame}: "
            "canonical matrix requires shear after removing PreRotation"
        )

    scale_values = [float(linear.col[index].length) for index in range(3)]
    if any(value <= 1e-10 for value in scale_values):
        raise RuntimeError(f"FBX inverse encoder found degenerate scale for {bone_name} frame {frame}: {scale_values}")

    normalized = linear.copy()
    for index, value in enumerate(scale_values):
        normalized.col[index] /= value
    if float(normalized.determinant()) < 0.0:
        raise RuntimeError(
            f"FBX inverse encoder does not yet support negative/reflected scale for {bone_name} frame {frame}"
        )

    rotation_matrix = (
        normalized
        @ post_rotation.to_3x3()
        @ rotation_alt.to_3x3().inverted_safe()
    )
    if abs(float(rotation_matrix.determinant()) - 1.0) > ORTHOGONAL_TOLERANCE:
        raise RuntimeError(
            f"FBX inverse encoder recovered non-rotation matrix for {bone_name} frame {frame}; "
            f"det={float(rotation_matrix.determinant()):.12g}"
        )

    if previous_euler is None:
        compatibility = Euler(
            tuple(math.radians(float(value)) for value in stack["Lcl Rotation"]),
            rotation_order,
        )
    else:
        compatibility = previous_euler
    euler = rotation_matrix.to_euler(rotation_order, compatibility)
    rotation_values = [math.degrees(float(value)) for value in euler]
    reconstructed_rotation = euler.to_matrix().to_4x4()

    rotation_offset = _translation(stack["RotationOffset"])
    rotation_pivot = _translation(stack["RotationPivot"])
    scaling_offset = _translation(stack["ScalingOffset"])
    scaling_pivot = _translation(stack["ScalingPivot"])
    scale_matrix = _scale(scale_values)

    static_after_translation = (
        rotation_offset
        @ rotation_pivot
        @ pre_rotation
        @ reconstructed_rotation
        @ rotation_alt
        @ post_rotation.inverted_safe()
        @ rotation_pivot.inverted_safe()
        @ scaling_offset
        @ scaling_pivot
        @ scale_matrix
        @ scaling_pivot.inverted_safe()
    )
    translation_matrix = base_target @ static_after_translation.inverted_safe()
    identity_error = _max_identity_3x3_error(translation_matrix)
    if identity_error > ENCODE_RESIDUAL_TOLERANCE:
        raise RuntimeError(
            f"FBX inverse encoder could not isolate pure translation for {bone_name} frame {frame}; "
            f"linearResidual={identity_error:.12g}"
        )
    translation_values = [float(value) for value in translation_matrix.translation]

    base_reconstructed = Matrix.Translation(Vector(translation_values)) @ static_after_translation
    basis_reconstructed = pre_adapter @ base_reconstructed @ geometry @ post_adapter
    residual = matrix_residual(target_basis, basis_reconstructed)
    if residual > ENCODE_RESIDUAL_TOLERANCE:
        raise RuntimeError(
            f"FBX inverse encoder residual exceeds tolerance for {bone_name} frame {frame}: "
            f"residual={residual:.12g} > {ENCODE_RESIDUAL_TOLERANCE:.12g}"
        )

    return translation_values, rotation_values, scale_values, euler.copy()


def derive_fbx_curves(
    rig_fbx: dict[str, Any],
    animation_fbx: dict[str, Any],
    frames: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    key_times = list(animation_fbx["sampleKeyTimes"])
    if len(key_times) != len(frames):
        raise RuntimeError(
            f"FBX sample timeline/frame mismatch: keyTimes={len(key_times)} frames={len(frames)}"
        )

    by_key: dict[tuple[str, str, str], list[float]] = {}
    previous_eulers: dict[str, Euler] = {}
    axis_names = ("x", "y", "z")

    for frame_entry in frames:
        frame = int(frame_entry["frame"])
        for bone_name, payload in rig_fbx["bones"].items():
            stack = payload["transformStack"]
            adapter = payload.get("encodingAdapter")
            target = trs_to_matrix(frame_entry["bones"][bone_name])
            if adapter is None:
                residual = matrix_residual(target, Matrix.Identity(4))
                if residual > ENCODE_RESIDUAL_TOLERANCE:
                    raise RuntimeError(
                        f"FBX inverse encoder lacks static encodingAdapter for animated bone {bone_name!r}; "
                        f"frame={frame} identityResidual={residual:.12g}"
                    )
                translation_values = [float(value) for value in stack["Lcl Translation"]]
                rotation_values = [float(value) for value in stack["Lcl Rotation"]]
                scale_values = [float(value) for value in stack["Lcl Scaling"]]
            else:
                translation_values, rotation_values, scale_values, previous = _derive_lcl_trs(
                    target,
                    stack,
                    adapter,
                    previous_eulers.get(bone_name),
                    bone_name=bone_name,
                    frame=frame,
                )
                previous_eulers[bone_name] = previous

            for property_name, values in (
                ("translation", translation_values),
                ("rotation", rotation_values),
                ("scale", scale_values),
            ):
                for axis_index, axis_name in enumerate(axis_names):
                    by_key.setdefault((bone_name, property_name, axis_name), []).append(float(values[axis_index]))

    return [
        {
            "bone": bone,
            "property": property_name,
            "axis": axis,
            "keyTimes": key_times,
            "keyValues": values,
        }
        for (bone, property_name, axis), values in sorted(by_key.items())
    ]


def _patch_global_settings(root, settings: dict[str, Any]) -> None:
    global_settings = native._find_first(root, b"GlobalSettings")
    if global_settings is None:
        raise RuntimeError("Generated FBX lacks GlobalSettings")
    props70 = native._find_first(global_settings, b"Properties70")
    if props70 is None:
        raise RuntimeError("Generated FBX GlobalSettings lacks Properties70")
    for name, value in settings.items():
        prop = native._parsed_property(props70, name)
        if prop is None or len(prop.props) < 5:
            raise RuntimeError(f"Generated FBX GlobalSettings lacks {name}")
        prop.props[-1] = value


def _patch_stack_layer_names(root, stack_name: str, layer_name: str) -> None:
    table = native._node_table(root)
    stacks = [elem for elem in table.values() if elem.id == b"AnimationStack"]
    layers = [elem for elem in table.values() if elem.id == b"AnimationLayer"]
    if len(stacks) != 1 or len(layers) != 1:
        raise RuntimeError(
            f"Generated FBX must contain exactly one stack/layer; stacks={len(stacks)} layers={len(layers)}"
        )
    stacks[0].props[-2] = stack_name.encode() + b"\x00\x01AnimStack"
    layers[0].props[-2] = layer_name.encode() + b"\x00\x01AnimLayer"


def _replace_curve_samples(curve, times: list[int], values: list[float]) -> None:
    if len(times) != len(values) or not times:
        raise RuntimeError("FBX encoder requires non-empty equal-length keyTimes/keyValues")
    key_time = native._find_first(curve, b"KeyTime")
    key_value = native._find_first(curve, b"KeyValueFloat")
    if key_time is None or key_value is None or not key_time.props or not key_value.props:
        raise RuntimeError(f"Generated FBX curve {native._name(curve)!r} lacks key arrays")
    existing_times = key_time.props[0]
    existing_values = key_value.props[0]
    key_time.props[0] = array.array(existing_times.typecode, [int(value) for value in times])
    key_value.props[0] = array.array(existing_values.typecode, [float(value) for value in values])


def _normalize_container_curves(
    root,
    target_curves: dict[tuple[str, str, str], Any],
    canonical_keys: set[tuple[str, str, str]],
    key_times: list[int],
) -> None:
    """Prevent the Blender-generated FBX container from carrying motion authority.

    Canonical bone T/R/S curves are replaced from animation.frames. Any other
    generated curve must be constant; we retime that constant onto the canonical
    KTime samples. A varying non-canonical curve would be independent motion and
    therefore fails closed instead of silently surviving the container export.
    """

    normalized_ids: set[int] = set()
    for key, curve in target_curves.items():
        curve_id = int(curve.props[0])
        if key in canonical_keys:
            normalized_ids.add(curve_id)
            continue
        _times, values = native._curve_arrays(curve)
        spread = max(values) - min(values)
        if spread > CONTAINER_CONSTANT_TOLERANCE:
            raise RuntimeError(
                "Generated FBX contains non-canonical varying transform curve; "
                f"key={key} valueSpread={spread:.12g}. "
                "animation.frames must remain the sole motion authority."
            )
        value = float(values[0])
        _replace_curve_samples(curve, key_times, [value] * len(key_times))
        normalized_ids.add(curve_id)

    # Also guard curves that are not recognizable as Model Lcl T/R/S. They are
    # allowed only when constant, and are retimed so they cannot extend the
    # reconstructed action range beyond the canonical sample timeline.
    for elem in native._node_table(root).values():
        if elem.id != b"AnimationCurve":
            continue
        curve_id = int(elem.props[0])
        if curve_id in normalized_ids:
            continue
        _times, values = native._curve_arrays(elem)
        spread = max(values) - min(values)
        if spread > CONTAINER_CONSTANT_TOLERANCE:
            raise RuntimeError(
                "Generated FBX contains unmapped varying AnimationCurve "
                f"{native._name(elem)!r}; valueSpread={spread:.12g}. "
                "Refusing a second motion authority outside animation.frames."
            )
        value = float(values[0])
        _replace_curve_samples(elem, key_times, [value] * len(key_times))


def encode_generated_fbx(
    generated_path: Path,
    output_path: Path,
    rig_fbx: dict[str, Any],
    animation_fbx: dict[str, Any],
    frames: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Encode canonical frames into FBX Lcl T/R/S using only static FBX metadata.

    No source animation curve values are accepted or read by this function.
    """

    curves = derive_fbx_curves(rig_fbx, animation_fbx, frames)
    root, _generated_version = parse_fbx.parse(str(generated_path), use_namedtuple=True)
    models = {native._name(elem): elem for elem in native._objects(root) if elem.id == b"Model"}
    expected_bones = set(rig_fbx["bones"])
    missing = sorted(expected_bones - set(models))
    if missing:
        raise RuntimeError(f"Generated FBX is missing rig bone Models required by canonical rig: {missing}")

    for bone_name, payload in rig_fbx["bones"].items():
        native._patch_model_transform(models[bone_name], payload["transformStack"])
    _patch_global_settings(root, rig_fbx["globalSettings"])
    native._patch_timebase(
        root,
        int(rig_fbx["fbxVersion"]),
        int(animation_fbx.get("ktimeTicksPerSecond", 46_186_158_000)),
    )
    native._patch_stack_timing(root, animation_fbx["stackTiming"])
    _patch_stack_layer_names(root, animation_fbx["stack"], animation_fbx["layer"])

    target_curves = native._target_curve_map(root)
    canonical_keys: set[tuple[str, str, str]] = set()
    for curve in curves:
        key = (curve["bone"], curve["property"], curve["axis"])
        target = target_curves.get(key)
        if target is None:
            raise RuntimeError(f"Generated FBX is missing animation curve required by derived canonical data: {key}")
        _replace_curve_samples(target, curve["keyTimes"], curve["keyValues"])
        canonical_keys.add(key)

    _normalize_container_curves(
        root,
        target_curves,
        canonical_keys,
        list(animation_fbx["sampleKeyTimes"]),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    encode_bin.write(
        str(output_path),
        native._clone_for_encoder(root),
        int(rig_fbx["fbxVersion"]),
    )
    return curves
