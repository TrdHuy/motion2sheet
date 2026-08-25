"""Blender-native VFX renderer V31: fixed V30 visibility dispatch."""
from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path

import bpy

_V30_PATH = Path(__file__).with_name("native_generate_vfx_v30.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v30", _V30_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load V30")
v30 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v30)

v29, v28, v27, v23 = v30.v29, v30.v28, v30.v27, v30.v23
v21, v19, v18, v17, v16, v14 = v30.v21, v30.v19, v30.v18, v30.v17, v30.v16, v30.v14
v12, v9, v8, v7, v6, base = v30.v12, v30.v9, v30.v8, v30.v7, v30.v6, v30.base


def setup_scene(spec):
    scene, layers = v30.setup_scene(spec)
    scene["vfx_renderer"] = "blender-native-v31"
    scene["vfx_visibility_dispatch"] = "v28-baseline-plus-v30-f6-no-recursion"
    return scene, layers


def tri_visibility(u, v, tier, p, seed, index, frames, tri):
    # V29 delegates every non-F6 sample directly to V28. Calling the mutable
    # v29.tri_visibility symbol here would recurse after monkey-patching it,
    # so dispatch explicitly to V28 for all baseline/non-F6 samples.
    if index != frames - 3:
        return v28.tri_visibility(u, v, tier, p, seed, index, frames, tri)
    if tier != "body":
        return 1.0
    rng = random.Random(seed * 32452843 + 2801)
    best = 99.0
    for _ in range(2):
        cu = rng.uniform(.24, .78)
        cv = rng.uniform(.62, .90)
        ru = rng.uniform(.045, .075)
        rv = rng.uniform(.050, .085)
        ang = rng.uniform(-.75, .75)
        ca, sa = math.cos(ang), math.sin(ang)
        du, dv = u - cu, v - cv
        xu = du * ca + dv * sa
        yv = -du * sa + dv * ca
        d = (xu / ru) ** 2 + (yv / rv) ** 2
        phase = rng.uniform(0.0, math.tau)
        edge = .10 * math.sin(math.tau * (3.7 * u + 2.4 * v) + phase)
        edge += .04 * math.sin(math.tau * (8.2 * u - 3.8 * v) + phase * .43)
        best = min(best, d + edge)
    return 0.0 if best < .72 else 1.0


def embed_sources(spec):
    v30.embed_sources(spec)
    try:
        text = bpy.data.texts.new("SOURCE_native_generate_vfx_v31.py")
        text.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError:
        pass

# V29's high-resolution add_ribbon resolves tri_visibility in V29's module
# globals, therefore update both V29 and V9 after importing V30.
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
