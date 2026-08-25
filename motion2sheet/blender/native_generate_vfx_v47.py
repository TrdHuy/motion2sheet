"""Blender-native VFX renderer V47: configurable point trajectories.

V47 keeps V46 visual behavior as the default. When source.json contains a
trajectory object, all path-aware VFX geometry samples that trajectory inside
Blender; the outer CLI only validates and transports configuration.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import bpy

_V46_PATH = Path(__file__).with_name("native_generate_vfx_v46.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v46", _V46_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load V46")
v46 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v46)

_TRAJECTORY_PATH = Path(__file__).with_name("vfx_trajectory.py")
_TRAJECTORY_SPEC = importlib.util.spec_from_file_location("motion2sheet_vfx_trajectory", _TRAJECTORY_PATH)
if _TRAJECTORY_SPEC is None or _TRAJECTORY_SPEC.loader is None:
    raise RuntimeError("Unable to load Blender trajectory module")
trajectory_lib = importlib.util.module_from_spec(_TRAJECTORY_SPEC)
_TRAJECTORY_SPEC.loader.exec_module(trajectory_lib)

v45 = v46.v45
v44 = v45.v44
v43 = v44.v43
v42 = v43.v42
v41 = v42.v41
v40 = v41.v40
v16 = v40.v16
v12, v9, v8, v7, base = v40.v12, v40.v9, v40.v8, v40.v7, v40.base

_ACTIVE_TRAJECTORY = trajectory_lib.BlenderTrajectory(None)


def configure_trajectory(spec):
    global _ACTIVE_TRAJECTORY
    _ACTIVE_TRAJECTORY = trajectory_lib.BlenderTrajectory(spec.get("trajectory"))
    return _ACTIVE_TRAJECTORY


def point_on_spine(radius, t, params):
    return _ACTIVE_TRAJECTORY.point_on_spine(radius, t, params)


def sample_trajectory(radius, t, params):
    """Public Blender-side trajectory API: position + tangent + normal."""
    return _ACTIVE_TRAJECTORY.sample(radius, t, params)


def setup_scene(spec):
    trajectory = configure_trajectory(spec)
    scene, layers = v46.setup_scene(spec)
    scene["vfx_renderer"] = "blender-native-v47"
    scene["vfx_trajectory_provider"] = trajectory.kind
    scene["vfx_trajectory_sampling"] = "blender-native-catmull-rom"
    scene["vfx_trajectory_point_count"] = len(trajectory.points)
    return scene, layers


def embed_sources(spec):
    v46.embed_sources(spec)
    for name, path in (
        ("SOURCE_native_generate_vfx_v47.py", Path(__file__)),
        ("SOURCE_vfx_trajectory.py", _TRAJECTORY_PATH),
    ):
        try:
            text = bpy.data.texts.new(name)
            text.write(path.read_text(encoding="utf-8"))
        except OSError:
            pass


# Patch the shared sampling seam used by legacy and polished renderer layers.
# Functions that reference v16.point_on_spine dynamically automatically follow
# this provider; older helpers stored the callable directly and are repatched.
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
