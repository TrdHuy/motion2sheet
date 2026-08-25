"""Blender-native VFX renderer V28: compact organic F6 cavities and richer electrical polish."""
from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path

import bpy

_V27_PATH = Path(__file__).with_name("native_generate_vfx_v27.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v27", _V27_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load V27")
v27 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v27)

v26, v25, v24, v23 = v27.v26, v27.v25, v27.v24, v27.v23
v21, v19, v18, v17, v16, v14 = v27.v21, v27.v19, v27.v18, v27.v17, v27.v16, v27.v14
v12, v9, v8, v7, v6, base = v27.v12, v27.v9, v27.v8, v27.v7, v27.v6, v27.base


def setup_scene(spec):
    scene, layers = v27.setup_scene(spec)
    scene["vfx_renderer"] = "blender-native-v28"
    scene["vfx_lightning_model"] = "five-varied-bolts-plus-dense-micro-electricity"
    scene["vfx_ignition_model"] = "blue-supported-starburst-at-shared-anchor"
    scene["vfx_f6_transition"] = "compact-rotated-organic-cavities"
    return scene, layers


def add_ignition(prefix, p, radius, materials, layers, seed, index, frames):
    v27.add_ignition(prefix, p, radius, materials, layers, seed, index, frames)
    nominal = float(p["thickness"]) * float(p["shape.body_scale"])
    x, y, _ = v16.point_on_spine(radius, .55, p)
    # Add broad blue/cyan electrical support behind the white starburst so F1
    # reads as an energy ignition instead of a thin white spark.
    for ri in range(10):
        rng = random.Random(seed*3133709 + ri*1013)
        ang = rng.uniform(0, math.tau)
        length = radius*rng.uniform(.24, .72)
        dx, dy = math.cos(ang), math.sin(ang)
        px, py = -dy, dx
        pts=[]
        for si in range(6):
            q=si/5.0
            bend=rng.uniform(-1,1)*length*.045*math.sin(math.pi*q)
            pts.append((x+dx*length*q+px*bend, y+dy*length*q+py*bend))
        rootw=nominal*rng.uniform(.025,.070)
        ws=[max(.0012,rootw*((1-i/5.)**1.12)) for i in range(6)]
        mat = materials["inner"] if ri % 3 == 0 else materials["body"]
        glow = materials["inner_glow"] if ri % 3 == 0 else materials["body_glow"]
        base.add_curve(f"{prefix}_support_glow_{ri}", pts, [w*3.0 for w in ws], glow, layers["PLASMA"], z=.58, frame=index+1, frames=frames)
        base.add_curve(f"{prefix}_support_{ri}", pts, [w*1.35 for w in ws], mat, layers["WISPS"], z=.63, frame=index+1, frames=frames)


def add_lightning(prefix, p, radius, tail, head, energy, breakup, materials, layers, seed, index, frames):
    local = dict(p)
    local["lightning.major_count"] = max(3, int(p["lightning.major_count"]) + 1)
    local["lightning.micro_count"] = max(24, int(p["lightning.micro_count"]))
    local["lightning.surface_crack_count"] = max(16, int(p["lightning.surface_crack_count"]))
    v27.add_lightning(prefix, local, radius, tail, head, energy, breakup, materials, layers, seed, index, frames)


def tri_visibility(u, v, tier, p, seed, index, frames, tri):
    if index != frames - 3:
        return v27.tri_visibility(u, v, tier, p, seed, index, frames, tri)
    if tier == "core":
        return 1.0

    rng = random.Random(seed*32452843 + 827)
    cavity_count = 3 if tier == "body" else 2
    deepest = 99.0
    for ci in range(cavity_count):
        cu = rng.uniform(.18,.84)
        cv = rng.uniform(.16,.84)
        ru = rng.uniform(.055,.095)
        rv = rng.uniform(.045,.090)
        ang = rng.uniform(-.9,.9)
        ca, sa = math.cos(ang), math.sin(ang)
        du, dv = u-cu, v-cv
        xu = du*ca + dv*sa
        yv = -du*sa + dv*ca
        d = (xu/ru)**2 + (yv/rv)**2
        phase = rng.uniform(0,math.tau)
        organic = .12*math.sin(math.tau*(4.1*u+3.0*v)+phase) + .065*math.sin(math.tau*(8.7*u-4.6*v)+phase*.39)
        deepest = min(deepest, d + organic)
    cutoff = .82 if tier == "body" else .58
    return 0.0 if deepest < cutoff else 1.0


def embed_sources(spec):
    v27.embed_sources(spec)
    try:
        text=bpy.data.texts.new("SOURCE_native_generate_vfx_v28.py")
        text.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError:
        pass

v9.add_ignition = add_ignition
v21.add_lightning = add_lightning
v9.tri_visibility = tri_visibility
v6.motion_window = v27.motion_window
v18.add_core = v27.add_core
v17._band_polygon = v19._band_polygon
v12.point_on_spine=v16.point_on_spine; v9.point_on_spine=v16.point_on_spine; v8.point_on_spine=v16.point_on_spine; v7.point_on_spine=v16.point_on_spine; base.point_on_arc=v16.point_on_spine
base.setup_scene=setup_scene; base.make_materials=v14.make_materials; base.build_frame=v23.build_frame; base.embed_sources=embed_sources

if __name__ == "__main__":
    base.main()
