"""Blender-native VFX renderer V32: coordinated subtle F6 cavities."""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import bpy

_V31_PATH = Path(__file__).with_name("native_generate_vfx_v31.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v31", _V31_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load V31")
v31 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v31)

v30, v29, v28, v27, v23 = v31.v30, v31.v29, v31.v28, v31.v27, v31.v23
v21, v19, v18, v17, v16, v14 = v31.v21, v31.v19, v31.v18, v31.v17, v31.v16, v31.v14
v12, v9, v8, v7, v6, base = v31.v12, v31.v9, v31.v8, v31.v7, v31.v6, v31.base


def setup_scene(spec):
    scene, layers = v31.setup_scene(spec)
    scene["vfx_renderer"] = "blender-native-v32"
    scene["vfx_f6_transition"] = "coordinated-small-organic-holes-with-live-core"
    return scene, layers


def _organic_ellipse(u, v, cu, cv, ru, rv, phase):
    du, dv = u - cu, v - cv
    d = (du / ru) ** 2 + (dv / rv) ** 2
    d += .10 * math.sin(math.tau * (3.2 * u + 2.6 * v) + phase)
    d += .035 * math.sin(math.tau * (7.4 * u - 4.1 * v) + phase * .41)
    return d


def tri_visibility(u, v, tier, p, seed, index, frames, tri):
    if index != frames - 3:
        return v28.tri_visibility(u, v, tier, p, seed, index, frames, tri)
    if tier == "core":
        return 1.0

    # Coordinate the holes across overlapping shell ribbons. V31 used a
    # different name-derived dissolve seed per ribbon, which made the openings
    # reveal another intact layer and visually disappear. Shared centers make
    # F6 show a few real cavities while preserving the live cyan/white core.
    if tier == "body":
        fields = (
            _organic_ellipse(u, v, .43, .72, .070, .105, .35),
            _organic_ellipse(u, v, .69, .82, .052, .078, 1.65),
        )
        return 0.0 if min(fields) < .76 else 1.0

    # Inner layer gets only one smaller opening around the first cavity. The
    # second cavity remains shell-only, keeping F6 mostly coherent.
    field = _organic_ellipse(u, v, .43, .50, .036, .060, .82)
    return 0.0 if field < .62 else 1.0


def embed_sources(spec):
    v31.embed_sources(spec)
    try:
        text = bpy.data.texts.new("SOURCE_native_generate_vfx_v32.py")
        text.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError:
        pass

v29.tri_visibility = tri_visibility
v9.tri_visibility = tri_visibility
v9.add_ribbon = v29.add_ribbon
v8.add_fragments = v29.add_fragments
v9.add_ignition = v30.add_ignition
v21.add_lightning = v28.add_lightning
v6.motion_window = v27.motion_window
v18.add_core = v27.add_core
v17._band_polygon = v19._band_polygon
v12.point_on_spine = v16.point_on_spine; v9.point_on_spine = v16.point_on_spine; v8.point_on_spine = v16.point_on_spine; v7.point_on_spine = v16.point_on_spine; base.point_on_arc = v16.point_on_spine
base.setup_scene = setup_scene; base.make_materials = v14.make_materials; base.build_frame = v23.build_frame; base.embed_sources = embed_sources

if __name__ == "__main__":
    base.main()
