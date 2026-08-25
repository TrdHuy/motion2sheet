"""Blender-native VFX renderer V35: denser multi-scale lightning hierarchy."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import bpy

_V34_PATH = Path(__file__).with_name("native_generate_vfx_v34.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v34", _V34_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load V34")
v34 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v34)

v33, v32, v31, v30, v29, v28, v27, v23 = v34.v33, v34.v32, v34.v31, v34.v30, v34.v29, v34.v28, v34.v27, v34.v23
v21, v19, v18, v17, v16, v14 = v34.v21, v34.v19, v34.v18, v34.v17, v34.v16, v34.v14
v12, v9, v8, v7, v6, base = v34.v12, v34.v9, v34.v8, v34.v7, v34.v6, v34.base


def setup_scene(spec):
    scene, layers = v34.setup_scene(spec)
    scene["vfx_renderer"] = "blender-native-v35"
    scene["vfx_lightning_model"] = "six-major-varied-bolts-plus-dense-medium-micro-hierarchy"
    return scene, layers


def add_lightning(prefix, p, radius, tail, head, energy, breakup, materials, layers, seed, index, frames):
    # Keep V27's rooted lightning topology but push the art direction toward
    # the contract: more readable bolts, stronger length/width variance, and
    # a denser bed of small electrical cracks without turning into a forest.
    local = dict(p)
    local["lightning.major_count"] = 6
    local["lightning.micro_count"] = max(34, int(p["lightning.micro_count"]))
    local["lightning.surface_crack_count"] = max(24, int(p["lightning.surface_crack_count"]))
    local["lightning.jitter"] = max(.66, float(p["lightning.jitter"]))
    local["lightning.spread"] = max(1.02, float(p["lightning.spread"]))
    local["lightning.branch_probability"] = max(.70, float(p["lightning.branch_probability"]))
    local["lightning.length"] = max(1.18, float(p["lightning.length"]))
    local["lightning.minor_width_ratio"] = max(.44, float(p["lightning.minor_width_ratio"]))
    local["lightning.minor_length_ratio"] = max(.60, float(p["lightning.minor_length_ratio"]))
    v27.add_lightning(prefix, local, radius, tail, head, energy, breakup, materials, layers, seed, index, frames)


def embed_sources(spec):
    v34.embed_sources(spec)
    try:
        text = bpy.data.texts.new("SOURCE_native_generate_vfx_v35.py")
        text.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError:
        pass

v29.tri_visibility = v32.tri_visibility
v9.tri_visibility = v32.tri_visibility
v9.add_ribbon = v29.add_ribbon
v8.add_fragments = v29.add_fragments
v9.add_ignition = v30.add_ignition
v21.add_lightning = add_lightning
v6.motion_window = v27.motion_window
v18.add_core = v33.add_core
v17._band_polygon = v19._band_polygon
v12.point_on_spine = v16.point_on_spine; v9.point_on_spine = v16.point_on_spine; v8.point_on_spine = v16.point_on_spine; v7.point_on_spine = v16.point_on_spine; base.point_on_arc = v16.point_on_spine
base.setup_scene = setup_scene; base.make_materials = v14.make_materials; base.build_frame = v23.build_frame; base.embed_sources = embed_sources

if __name__ == "__main__":
    base.main()
