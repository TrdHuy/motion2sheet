"""Blender-native VFX renderer V40: curved residual motion-memory fragments for F7/F8."""
from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path

import bpy

_V39_PATH = Path(__file__).with_name("native_generate_vfx_v39.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v39", _V39_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load V39")
v39 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v39)

v38, v37 = v39.v38, v39.v37
v36, v35, v33, v32, v29, v27, v23 = v39.v36, v39.v35, v39.v33, v39.v32, v39.v29, v39.v27, v39.v23
v21, v18, v17, v16, v14 = v39.v21, v39.v18, v39.v17, v39.v16, v39.v14
v9, v8, v7, v6, base = v39.v9, v39.v8, v39.v7, v39.v6, v39.base
_ORIG_BUILD_FRAME = v39.build_frame


def setup_scene(spec):
    scene, layers = v39.setup_scene(spec)
    scene["vfx_renderer"] = "blender-native-v40"
    scene["vfx_terminal_fragment_model"] = "short-curved-spine-memory-arcs"
    return scene, layers


def add_motion_memory(prefix, p, radius, materials, layers, seed, index, frames):
    if index not in (frames-2, frames-1):
        return
    nominal = float(p["thickness"]) * float(p["shape.body_scale"])
    final = index == frames-1
    count = 7 if final else 12

    for fi in range(count):
        rng = random.Random(seed*2147483647 + index*65537 + fi*8191)
        center = rng.uniform(.10,.91)
        span = rng.uniform(.028,.070) if final else rng.uniform(.035,.092)
        start = max(.015, center-span*.5)
        end = min(.985, center+span*.5)
        steps = rng.randint(7,12)
        normal_offset = nominal*rng.uniform(-.55,1.20)
        tangent_drift = radius*rng.uniform(-.018,.030)*(1.15 if final else .78)
        phase = rng.uniform(0.0,math.tau)
        pts=[]; widths=[]
        rootw = nominal*rng.uniform(.035,.090)*(0.76 if final else 1.0)
        for si in range(steps):
            q=si/(steps-1)
            u=start+(end-start)*q
            x,y,a=v16.point_on_spine(radius,u,p)
            nx,ny=math.cos(a),math.sin(a); tx,ty=-math.sin(a),math.cos(a)
            local_off=normal_offset + nominal*.14*math.sin(math.pi*q+phase)
            drift=tangent_drift*(q-.5) + nominal*.035*math.sin(math.tau*1.35*q+phase*.47)
            x += nx*local_off + tx*drift
            y += ny*local_off + ty*drift
            pts.append((x,y))
            env=math.sin(math.pi*q)**.42
            pulse=.82+.20*math.sin(math.tau*1.15*q+phase)
            widths.append(max(.0011,rootw*env*pulse))

        # Mostly cyan/blue residuals; a minority keep tiny white-hot energy in F7.
        hot = (not final) and fi < 3
        cyan = (fi % 3 == 0) or hot
        body_mat = materials["core"] if hot else (materials["inner"] if cyan else materials["body"])
        glow_mat = materials["core_glow"] if hot else (materials["inner_glow"] if cyan else materials["body_glow"])
        glow_mult = 2.4 if hot else 2.1
        base.add_curve(f"{prefix}_memory_glow_{fi}",pts,[w*glow_mult for w in widths],glow_mat,layers["PLASMA"],z=.60,frame=index+1,frames=frames)
        base.add_curve(f"{prefix}_memory_{fi}",pts,widths,body_mat,layers["WISPS"],z=.67,frame=index+1,frames=frames)

    # Tiny detached sparks around the residual curve, sparse rather than explosive.
    spark_count = 8 if final else 12
    for si in range(spark_count):
        rng=random.Random(seed*49979687 + index*10009 + si*4051)
        u=rng.uniform(.12,.90)
        x,y,a=v16.point_on_spine(radius,u,p)
        nx,ny=math.cos(a),math.sin(a); tx,ty=-math.sin(a),math.cos(a)
        x += nx*nominal*rng.uniform(-.8,1.6) + tx*nominal*rng.uniform(-.5,.5)
        y += ny*nominal*rng.uniform(-.8,1.6) + ty*nominal*rng.uniform(-.5,.5)
        length=radius*rng.uniform(.015,.045)*(0.75 if final else 1.0)
        ang=a-math.pi*.5+rng.uniform(-1.0,1.0)
        dx,dy=math.cos(ang),math.sin(ang)
        pts=[(x,y),(x+dx*length,y+dy*length)]
        w=nominal*rng.uniform(.010,.026)
        base.add_curve(f"{prefix}_memory_spark_{si}",pts,[w,max(.0007,w*.12)],materials["inner"],layers["WISPS"],z=.70,frame=index+1,frames=frames)


def build_frame(spec,index,materials,layers):
    _ORIG_BUILD_FRAME(spec,index,materials,layers)
    p=spec["params"]; frames=int(spec["frames"]); radius=float(p["radius"])
    add_motion_memory(f"F{index+1:02d}",p,radius,materials,layers,int(spec["seed"]),index,frames)


def embed_sources(spec):
    v39.embed_sources(spec)
    try:
        text=bpy.data.texts.new("SOURCE_native_generate_vfx_v40.py")
        text.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError:
        pass

v29.tri_visibility=v32.tri_visibility
v9.tri_visibility=v32.tri_visibility
v9.add_ribbon=v29.add_ribbon
v8.add_fragments=v29.add_fragments
v9.add_ignition=v37.add_ignition
v21.add_lightning=v35.add_lightning
v6.motion_window=v27.motion_window
v18.add_core=v33.add_core
v17._band_polygon=v36.band_polygon
v9.point_on_spine=v16.point_on_spine; v8.point_on_spine=v16.point_on_spine; v7.point_on_spine=v16.point_on_spine; base.point_on_arc=v16.point_on_spine
base.setup_scene=setup_scene; base.make_materials=v14.make_materials; base.build_frame=build_frame; base.embed_sources=embed_sources

if __name__=="__main__":
    base.main()
