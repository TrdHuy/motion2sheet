"""Blender-native VFX renderer V39: add organic plasma tongues and aura around the powered slash."""
from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path

import bpy

_V38_PATH = Path(__file__).with_name("native_generate_vfx_v38.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v38", _V38_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load V38")
v38 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v38)

v37 = v38.v37
v36, v35, v33, v32, v29, v27, v23 = v37.v36, v37.v35, v37.v33, v37.v32, v37.v29, v37.v27, v37.v23
v21, v18, v17, v16, v14 = v37.v21, v37.v18, v37.v17, v37.v16, v37.v14
v9, v8, v7, v6, base = v37.v9, v37.v8, v37.v7, v37.v6, v37.base
_ORIG_BUILD_FRAME = v23.build_frame


def setup_scene(spec):
    scene, layers = v38.setup_scene(spec)
    scene["vfx_renderer"] = "blender-native-v39"
    scene["vfx_plasma_edge_model"] = "organic-tapered-tongues-plus-cyan-aura"
    return scene, layers


def add_plasma_tongues(prefix, p, radius, tail, head, energy, materials, layers, seed, index, frames):
    if index < 1 or index > 5 or energy < .50:
        return
    nominal = float(p["thickness"]) * float(p["shape.body_scale"])
    count = 12 if index <= 4 else 8
    strength = .72 + .28*energy

    for ti in range(count):
        rng = random.Random(seed*1103515245 + index*9176 + ti*7919)
        local = rng.uniform(.08, .92)
        u = tail + (head-tail)*local
        x, y, a = v16.point_on_spine(radius, u, p)
        nx, ny = math.cos(a), math.sin(a)
        tx, ty = -math.sin(a), math.cos(a)

        # Root slightly inside the outer shell, then peel outward with a
        # tangent-biased curve so these read as plasma tongues, not lightning.
        root_off = nominal*rng.uniform(.72, 1.30)
        x += nx*root_off; y += ny*root_off
        length = radius*rng.uniform(.10, .28)*strength*(1.0 if ti < 7 else .72)
        tangent_bias = rng.uniform(-.48, .48)
        curve = rng.uniform(-.30, .30)
        steps = rng.randint(9, 14)
        pts = []
        widths = []
        rootw = nominal*rng.uniform(.050, .105)*(1.0 if ti < 5 else .72)
        phase = rng.uniform(0.0, math.tau)
        for si in range(steps):
            q = si/(steps-1)
            bend = tangent_bias*length*(q**1.08)
            bend += curve*length*math.sin(math.pi*q)
            ripple = length*(.018*math.sin(math.tau*2.1*q+phase)+.008*math.sin(math.tau*5.3*q+phase*.41))*math.sin(math.pi*q)
            outward = length*(q**.92)
            pts.append((x + nx*outward + tx*(bend+ripple), y + ny*outward + ty*(bend+ripple)))
            env = (1.0-q)**rng.uniform(1.00,1.45)
            pulse = .88 + .16*math.sin(math.tau*rng.uniform(.8,1.8)*q + phase)
            widths.append(max(.0014, rootw*env*pulse))

        cyan = (ti % 4 == 0) or (ti < 3 and rng.random() < .45)
        glow_mat = materials["inner_glow"] if cyan else materials["body_glow"]
        body_mat = materials["inner"] if cyan else materials["body"]
        base.add_curve(f"{prefix}_plasma_tongue_glow_{ti}", pts, [w*3.0 for w in widths], glow_mat, layers["PLASMA"], z=.44, frame=index+1, frames=frames)
        base.add_curve(f"{prefix}_plasma_tongue_{ti}", pts, widths, body_mat, layers["WISPS"], z=.52, frame=index+1, frames=frames)

    # A few short cyan wisps live close to the hot seam and break the broad
    # flat body into smaller energetic regions without punching hard holes.
    for wi in range(6):
        rng = random.Random(seed*2654435761 + index*10007 + wi*4099)
        local = rng.uniform(.14,.86)
        u = tail + (head-tail)*local
        x,y,a = v16.point_on_spine(radius,u,p)
        nx,ny = math.cos(a),math.sin(a); tx,ty=-math.sin(a),math.cos(a)
        root_off = nominal*rng.uniform(.18,.52)
        x += nx*root_off; y += ny*root_off
        length = radius*rng.uniform(.055,.135)*strength
        steps = rng.randint(7,10)
        pts=[]; widths=[]
        sign = -1.0 if rng.random() < .5 else 1.0
        phase=rng.uniform(0,math.tau)
        rootw=nominal*rng.uniform(.025,.055)
        for si in range(steps):
            q=si/(steps-1)
            out=length*q
            tan=sign*length*.28*math.sin(math.pi*q)+length*.05*math.sin(math.tau*1.6*q+phase)
            pts.append((x+nx*out+tx*tan,y+ny*out+ty*tan))
            widths.append(max(.0012,rootw*((1-q)**1.25)))
        base.add_curve(f"{prefix}_cyan_wisp_glow_{wi}",pts,[w*2.6 for w in widths],materials["inner_glow"],layers["PLASMA"],z=.58,frame=index+1,frames=frames)
        base.add_curve(f"{prefix}_cyan_wisp_{wi}",pts,widths,materials["inner"],layers["WISPS"],z=.62,frame=index+1,frames=frames)


def build_frame(spec, index, materials, layers):
    _ORIG_BUILD_FRAME(spec, index, materials, layers)
    p = spec["params"]
    frames = int(spec["frames"])
    radius = float(p["radius"])
    tail, head, energy, breakup = v27.motion_window(index, frames, float(p["timing.peak"]))
    if breakup <= .30:
        add_plasma_tongues(f"F{index+1:02d}", p, radius, tail, head, energy, materials, layers, int(spec["seed"]), index, frames)


def embed_sources(spec):
    v38.embed_sources(spec)
    try:
        text = bpy.data.texts.new("SOURCE_native_generate_vfx_v39.py")
        text.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError:
        pass

v29.tri_visibility = v32.tri_visibility
v9.tri_visibility = v32.tri_visibility
v9.add_ribbon = v29.add_ribbon
v8.add_fragments = v29.add_fragments
v9.add_ignition = v37.add_ignition
v21.add_lightning = v35.add_lightning
v6.motion_window = v27.motion_window
v18.add_core = v33.add_core
v17._band_polygon = v36.band_polygon
v9.point_on_spine = v16.point_on_spine; v8.point_on_spine = v16.point_on_spine; v7.point_on_spine = v16.point_on_spine; base.point_on_arc = v16.point_on_spine
base.setup_scene = setup_scene; base.make_materials = v14.make_materials; base.build_frame = build_frame; base.embed_sources = embed_sources

if __name__ == "__main__":
    base.main()
