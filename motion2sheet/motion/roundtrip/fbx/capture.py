from __future__ import annotations

import math
from contextlib import contextmanager
from typing import Any, Iterator

from mathutils import Euler, Matrix


def _flat_matrix(matrix: Matrix) -> list[float]:
    return [float(matrix[row][column]) for row in range(4) for column in range(4)]


def _geometry_matrix(transform_data) -> Matrix:
    location = Matrix.Translation(transform_data.geom_loc)
    rotation = Euler(
        tuple(math.radians(float(value)) for value in transform_data.geom_rot),
        "XYZ",
    ).to_matrix().to_4x4()
    scale = Matrix.Identity(4)
    for index, value in enumerate(transform_data.geom_sca):
        scale[index][index] = float(value)
    return location @ rotation @ scale


def _capture_adapter(item) -> dict[str, Any]:
    pre = item.get_bind_matrix().inverted_safe() if item.is_bone else Matrix.Identity(4)
    if item.pre_matrix:
        pre @= item.pre_matrix

    post = item.anim_compensation_matrix.copy() if item.anim_compensation_matrix else Matrix.Identity(4)
    if item.post_matrix:
        post @= item.post_matrix

    transform_data = item.fbx_transform_data
    return {
        "preMatrix": _flat_matrix(pre),
        "postMatrix": _flat_matrix(post),
        "geometryMatrix": _flat_matrix(_geometry_matrix(transform_data)),
        "rotationAltMatrix": _flat_matrix(transform_data.rot_alt_mat.to_4x4()),
    }


@contextmanager
def capture_blender_fbx_pose_adapters() -> Iterator[dict[str, dict[str, Any]]]:
    """Capture the static matrices Blender uses to map FBX node transforms to PoseBone.matrix_basis.

    These matrices are format/decoder metadata. They contain no animation samples and are stable for a
    given imported rig/source transform stack. The wrapper observes Blender's importer while it builds
    animation curves, but never records the source curve values.
    """

    from io_scene_fbx import import_fbx

    original = import_fbx._transformation_curves_gen
    captured: dict[str, dict[str, Any]] = {}

    def wrapped(item, values_arrays, channel_keys):
        if item.is_bone:
            name = str(item.bl_bone)
            adapter = _capture_adapter(item)
            previous = captured.get(name)
            if previous is not None and previous != adapter:
                raise RuntimeError(f"FBX importer produced inconsistent static pose adapter for bone {name!r}")
            captured[name] = adapter
        yield from original(item, values_arrays, channel_keys)

    import_fbx._transformation_curves_gen = wrapped
    try:
        yield captured
    finally:
        import_fbx._transformation_curves_gen = original
