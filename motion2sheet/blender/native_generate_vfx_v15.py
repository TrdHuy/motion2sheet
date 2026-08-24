"""Blender-native VFX renderer V15: segmented hot core + coherent terminal baseline."""
from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path

import bpy

_V14_PATH = Path(__file__).with_name("native_generate_vfx_v14.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v14", _V14_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load Blender-native V14 renderer")
v14 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v14)
v13, v12, v9, v8, v7, v6, base = v14.v13, v14.v12, v14.v9, v14.v8, v14.v7, v14.v6, v14.base


def setup_scene(spec):
    scene, layers = v14.setup_scene(spec)
    scene["vfx_renderer"] = "blender-native-v15"
    scene["vfx_core_model"] = "segmented-non-outline-hot-core"
    scene["vfx_terminal_baseline"] = "coherent-body-only"
    return scene, layers


def add_segmented_core(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup):
    heat=base.smoothstep((energy-.54)/.46)
    if heat<.02 or breakup>.67:
        return
    count=max(3,int(p["core.streak_count"]))
    nominal=float(p["thickness"])*float(p["shape.body_scale"])
    center_jitter=float(p["core.center_jitter"])/max(1.0,float(p["core.width_max"]))
    width_jitter=float(p["core.width_jitter"])
    streak_ratio=float(p["core.streak_width_ratio"])
    split=float(p["core.split_probability"])
    for s in range(count):
        rng=random.Random(seed*700001+s*8191+index*3571)
        # Each streak owns a different local interval instead of tracing the full body.
        start=max(.04, .05+s*.055+rng.uniform(-.035,.025))
        end=min(.96, start+rng.uniform(.43,.68))
        lane=-.34 + .12*s + rng.uniform(-.035,.035)
        phase=rng.uniform(0,math.tau)
        freq=rng.uniform(1.4,2.8)
        pts=[]; ws=[]
        for i in range(72):
            q=i/71.0
            local=start+(end-start)*q
            x,y,a=v12.point_on_spine(radius,tail+(head-tail)*local,p)
            nx,ny=math.cos(a),math.sin(a); tx,ty=-math.sin(a),math.cos(a)
            off=lane+center_jitter*(.22*math.sin(math.tau*freq*q+phase)+.08*math.sin(math.tau*3.1*q+phase*.41))
            x+=nx*nominal*off + tx*nominal*.035*math.sin(math.tau*2.35*q+phase)
            y+=ny*nominal*off + ty*nominal*.035*math.sin(math.tau*2.35*q+phase)
            env=(math.sin(math.pi*q)**.45)
            pinch=1.0
            for pc in (.25+.04*s,.54-.025*s,.76):
                d=abs(q-pc)
                if d<.045: pinch*=.16+.84*d/.045
            jitter=max(.22,1.0+width_jitter*.28*math.sin(math.tau*2.0*q+phase))
            w=nominal*streak_ratio*rng.uniform(.095,.14)*env*pinch*jitter*heat
            pts.append((x,y)); ws.append(max(.0010,w))
        # One or two real gaps per streak.
        gap_centers=[rng.uniform(.28,.72)]
        if rng.random()<split: gap_centers.append(rng.uniform(.18,.84))
        chunks=[]; cp=[]; cw=[]
        for i,(pt,w) in enumerate(zip(pts,ws)):
            q=i/71.0
            gap=any(abs(q-g)<rng.uniform(.018,.035) for g in gap_centers)
            if gap:
                if len(cp)>=3: chunks.append((cp,cw))
                cp=[]; cw=[]
            else:
                cp.append(pt); cw.append(w)
        if len(cp)>=3: chunks.append((cp,cw))
        for ci,(cpts,cws) in enumerate(chunks):
            base.add_curve(f"{prefix}_segcore_cyan_{s}_{ci}",cpts,[w*2.0 for w in cws],materials["inner_glow"],layers["PLASMA"],z=.57,frame=index+1,frames=frames)
            base.add_curve(f"{prefix}_segcore_white_{s}_{ci}",cpts,cws,materials["core"],layers["CORE"],z=.64,frame=index+1,frames=frames)


def build_frame(spec,index,materials,layers):
    p=spec["params"]; v14._ACTIVE_PARAMS=p
    radius=float(p["radius"]); frames=int(spec["frames"]); seed=int(spec["seed"])
    tail,head,energy,breakup=v6.motion_window(index,frames,float(p["timing.peak"]))
    prefix=f"F{index+1:02d}"
    if index==0:
        v9.add_ignition(prefix,p,radius,materials,layers,seed,index,frames); return
    active_dissolve=float(p["dissolve.strength"])>0.0
    final=index==frames-1
    removed=[]
    # Final powered baseline is intentionally one coherent support.  Active
    # dissolve erodes this same support and then adds detached shards.
    outer_scale=2.82 if final else 3.05
    removed += v9.add_ribbon(prefix+"_outer_glow","body",p,radius,tail,head,materials["outer_glow"],layers["PLASMA"],seed,index,frames,.02,outer_scale,.46,1.12)
    removed += v9.add_ribbon(prefix+"_outer","body",p,radius,tail,head,materials["outer"],layers["BODY"],seed+7,index,frames,.08,2.48,.32,1.10)
    removed += v9.add_ribbon(prefix+"_body","body",p,radius,tail,head,materials["body"],layers["BODY"],seed+31,index,frames,.14,1.46,.18,.96)
    removed += v9.add_ribbon(prefix+"_inner","inner",p,radius,tail,head,materials["inner"],layers["BODY"],seed+47,index,frames,.28,.16,.036,.58)

    # Decorations disappear in the last powered baseline; this keeps semantic
    # fragmentation about the dissolve itself rather than pre-existing wisps.
    if not final:
        v14.add_edge_tongues(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
        add_segmented_core(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
        v14.add_hotspots(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
        v12.add_lightning(prefix,p,radius,tail,head,energy,breakup,materials,layers,seed,index,frames)
    elif active_dissolve:
        # A few residual cyan/electric traces are allowed only in the active
        # terminal dissolve and are generated after the body has broken apart.
        v13.add_terminal_shards(prefix,p,radius,tail,head,materials,layers,seed,index,frames)

    v8.add_fragments(prefix,removed,p,materials,layers,radius,seed,index,frames,breakup)


def embed_sources(spec):
    v14.embed_sources(spec)
    try:
        text=bpy.data.texts.new("SOURCE_native_generate_vfx_v15.py")
        text.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError:
        pass


base.setup_scene=setup_scene
base.make_materials=v14.make_materials
base.build_frame=build_frame
base.embed_sources=embed_sources

if __name__ == "__main__":
    base.main()
