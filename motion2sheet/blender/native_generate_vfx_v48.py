"""Blender-native VFX renderer V48: 3D trajectory and conical helix support.

V48 preserves V47 output for legacy and 2D point configurations. 3D centerlines
are sampled exclusively inside Blender. Existing screen-facing VFX layers use the
XY projection of the centerline, while the authoritative source.blend also stores
an exact editable 3D trajectory guide with X/Y/Z coordinates.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import bpy

_V47_PATH = Path(__file__).with_name("native_generate_vfx_v47.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v47", _V47_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load V47")
v47 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v47)

_TRAJECTORY_PATH = Path(__file__).with_name("vfx_trajectory_v48.py")
_TRAJECTORY_SPEC = importlib.util.spec_from_file_location("motion2sheet_vfx_trajectory_v48", _TRAJECTORY_PATH)
if _TRAJECTORY_SPEC is None or _TRAJECTORY_SPEC.loader is None:
    raise RuntimeError("Unable to load V48 Blender trajectory module")
trajectory_lib = importlib.util.module_from_spec(_TRAJECTORY_SPEC)
_TRAJECTORY_SPEC.loader.exec_module(trajectory_lib)

v46 = v47.v46
v45 = v47.v45
v44 = v47.v44
v43 = v47.v43
v42 = v47.v42
v41 = v47.v41
v40 = v47.v40
v16 = v47.v16
v12 = v47.v12
v9, v8, v7, base = v47.v9, v47.v8, v47.v7, v47.base

_ACTIVE_TRAJECTORY = trajectory_lib.BlenderTrajectory3D(None)
_USE_V47_PROJECTED_SAMPLER = True


def configure_trajectory(spec):
    global _ACTIVE_TRAJECTORY, _USE_V47_PROJECTED_SAMPLER
    config = spec.get("trajectory")
    _ACTIVE_TRAJECTORY = trajectory_lib.BlenderTrajectory3D(config)
    _USE_V47_PROJECTED_SAMPLER = (
        config is None or
        (_ACTIVE_TRAJECTORY.kind == "points" and _ACTIVE_TRAJECTORY.dimensions == 2)
    )
    # Delegate legacy/2D sampling to the already-verified V47 provider so the
    # V48 feature cannot perturb accepted pixels through tiny floating changes.
    if _USE_V47_PROJECTED_SAMPLER:
        v47.configure_trajectory(spec)
    return _ACTIVE_TRAJECTORY


def point_on_spine(radius, t, params):
    if _USE_V47_PROJECTED_SAMPLER:
        return v47.point_on_spine(radius, t, params)
    return _ACTIVE_TRAJECTORY.point_on_spine(radius, t, params)


def sample_trajectory(radius, t, params):
    """Projected compatibility API used by existing screen-facing VFX layers."""
    if _USE_V47_PROJECTED_SAMPLER:
        x, y, tx, ty, nx, ny = v47.sample_trajectory(radius, t, params)
        return x, y, tx, ty, nx, ny, _ACTIVE_TRAJECTORY.scale_at(t)
    return _ACTIVE_TRAJECTORY.sample_projected(radius, t, params)


def sample_trajectory_3d(radius, t, params):
    """Full Blender-side centerline API: XYZ + tangent/normal/binormal + scale."""
    return _ACTIVE_TRAJECTORY.sample3d(radius, t, params)


def _add_trajectory_guide(spec, trajectory):
    """Store the canonical 3D path as editable non-rendering geometry in source.blend."""
    if trajectory.kind == "legacy":
        return
    radius = float(spec["params"]["radius"])
    curve = bpy.data.curves.new("VFX_Trajectory3D_Guide_Curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 1
    curve.bevel_depth = max(.002, radius * .0025)
    curve.bevel_resolution = 1
    spline = curve.splines.new("POLY")
    sample_count = max(64, len(trajectory.points) * 8)
    spline.points.add(sample_count - 1)
    for index, cp in enumerate(spline.points):
        t = index / max(1, sample_count - 1)
        x, y, z = trajectory.raw_position3d(radius, t, spec["params"])
        cp.co = (x, y, z, 1.0)
        cp.radius = trajectory.scale_at(t)
    obj = bpy.data.objects.new("VFX_Trajectory3D_Guide", curve)
    bpy.context.scene.collection.objects.link(obj)
    obj.hide_render = True
    obj["vfx_role"] = "authoritative-3d-trajectory-guide"
    obj["vfx_trajectory_provider"] = trajectory.kind
    obj["vfx_dimensions"] = trajectory.dimensions


def setup_scene(spec):
    trajectory = configure_trajectory(spec)
    scene, layers = v46.setup_scene(spec)
    scene["vfx_renderer"] = "blender-native-v48"
    scene["vfx_trajectory_provider"] = trajectory.kind
    scene["vfx_trajectory_sampling"] = "blender-native-catmull-rom-3d"
    scene["vfx_trajectory_dimensions"] = trajectory.dimensions
    scene["vfx_trajectory_point_count"] = len(trajectory.points)
    scene["vfx_trajectory_has_depth"] = trajectory.has_depth
    scene["vfx_trajectory_scale_start"] = trajectory.scale_start
    scene["vfx_trajectory_scale_end"] = trajectory.scale_end
    _add_trajectory_guide(spec, trajectory)
    return scene, layers


def embed_sources(spec):
    v46.embed_sources(spec)
    for name, path in (
        ("SOURCE_native_generate_vfx_v48.py", Path(__file__)),
        ("SOURCE_vfx_trajectory_v48.py", _TRAJECTORY_PATH),
    ):
        try:
            text = bpy.data.texts.new(name)
            text.write(path.read_text(encoding="utf-8"))
        except OSError:
            pass


# V48 owns the same shared sampling seam as V47, now backed by an XYZ path.
v16.point_on_spine = point_on_spine
v12.point_on_spine = point_on_spine
v9.point_on_spine = point_on_spine
v8.point_on_spine = point_on_spine
v7.point_on_spine = point_on_spine
base.point_on_arc = point_on_spine
base.setup_scene = setup_scene
base.embed_sources = embed_sources

if __name__ == "__main__":
    base.main()
