"""Blender-native VFX renderer V17: coherent polygon plasma body, late mesh breakup."""
from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path

import bpy

_V16_PATH=Path(__file__).with_name("native_generate_vfx_v16.py")
_SPEC=importlib.util.spec_from_file_location("motion2sheet_native_vfx_v16",_V16_PATH)
if _SPEC is None or _SPEC.loader is None: raise RuntimeError("Unable to load V16")
v16=importlib.util.module_from_spec(_SPEC); _SPEC.loader.exec_module(v16)
v15,v14,v13,v12,v9,v8,v7,v6,base=v16.v15,v16.v14,v16.v13,v16.v12,v16.v9,v16.v8,v16.v7,v16.v6,v16.base


def setup_scene(spec):
    scene,layers=v16.setup_scene(spec)
    scene["vfx_renderer"]="blender-native-v17"
    scene["vfx_body_model"]="coherent-noisy-polygons"
    scene["vfx_breakup_transition"]="polygon-to-eroded-mesh"
    return scene,layers


def _band_polygon(p,radius,tail,head,outer_scale,inner_scale,seed,phase_shift=0.0):
    rng=random.Random(seed); phase=rng.uniform(0,math.tau)+phase_shift; nominal=float(p["thickness"])*float(p["shape.body_scale"])
    outer=[]; inner=[]; samples=96
    edge=float(p["shape.edge_noise"]); ef=float(p["shape.edge_noise_frequency"]); detail=float(p["shape.detail_noise"]); df=float(p["shape.detail_noise_frequency"])
    for i in range(samples):
        q=i/(samples-1); u=tail+(head-tail)*q; x,y,a=v16.point_on_spine(radius,u,p); nx,ny=math.cos(a),math.sin(a); tx,ty=-math.sin(a),math.cos(a)
        env=(math.sin(math.pi*q)**max(.20,float(p["shape.taper_power"])))
        belly=math.exp(-((q-.55)/.25)**2); shoulder=math.exp(-((q-.23)/.15)**2); lower=math.exp(-((q-.79)/.16)**2)
        macro=(.66+1.03*belly+.27*shoulder+.34*lower)*(.52+.48*env)
        coarse=math.sin(math.tau*(ef*.078)*q+phase)+.45*math.sin(math.tau*(ef*.039)*q+phase*.53)
        fine=math.sin(math.tau*(df*.060)*q+phase*.37)
        ow=nominal*outer_scale*macro*(1+edge*.045*coarse+detail*.024*fine)
        iw=nominal*inner_scale*(.52+.18*belly)*(.46+.54*env)*(1+edge*.015*coarse-detail*.010*fine)
        # Low-frequency center drift makes each material layer independent.
        shift=nominal*(.075*math.sin(math.tau*1.32*q+phase)+.025*math.sin(math.tau*3.1*q+phase*.43))
        cx=x+nx*shift+tx*nominal*.020*math.sin(math.tau*1.1*q+phase)
        cy=y+ny*shift+ty*nominal*.020*math.sin(math.tau*1.1*q+phase)
        outer.append((cx+nx*ow,cy+ny*ow)); inner.append((cx-nx*iw,cy-ny*iw))
    return outer+list(reversed(inner))


def add_powered_mass(prefix,p,radius,tail,head,materials,layers,seed,index,frames):
    specs=(
        ("haze",3.10,.48,materials["outer_glow"],layers["PLASMA"],.03,0),
        ("outer",2.55,.34,materials["outer"],layers["BODY"],.08,17),
        ("body",1.55,.22,materials["body"],layers["BODY"],.14,31),
        ("inner",.72,.10,materials["inner"],layers["BODY"],.25,47),
    )
    for name,os,is_,mat,coll,z,off in specs:
        poly=_band_polygon(p,radius,tail,head,os,is_,seed+off,off*.013)
        base.add_polygon(f"{prefix}_mass_{name}",poly,mat,coll,z=z,frame=index+1,frames=frames)


def add_core(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup):
    heat=base.smoothstep((energy-.56)/.44)
    if heat<.02 or breakup>.62: return
    count=max(3,int(p["core.streak_count"])); nominal=float(p["thickness"])*float(p["shape.body_scale"]); ratio=float(p["core.streak_width_ratio"]); wj=float(p["core.width_jitter"])
    for s in range(count):
        rng=random.Random(seed*760001+s*9209+index*3571); start=rng.uniform(.06,.34); length=rng.uniform(.26,.48); end=min(.96,start+length); lane=.52+.18*s+rng.uniform(-.05,.05); phase=rng.uniform(0,math.tau); freq=rng.uniform(1.3,2.7)
        pts=[]; ws=[]
        for i in range(58):
            q=i/57.; local=start+(end-start)*q; x,y,a=v16.point_on_spine(radius,tail+(head-tail)*local,p); nx,ny=math.cos(a),math.sin(a); tx,ty=-math.sin(a),math.cos(a)
            off=lane+.14*math.sin(math.tau*freq*q+phase)+.045*math.sin(math.tau*3.2*q+phase*.41)
            x+=nx*nominal*off+tx*nominal*.055*math.sin(math.tau*2.25*q+phase); y+=ny*nominal*off+ty*nominal*.055*math.sin(math.tau*2.25*q+phase)
            env=math.sin(math.pi*q)**.40; pinch=1.
            for pc in (.28,.56,.78):
                d=abs(q-pc)
                if d<.045: pinch*=.12+.88*d/.045
            width=nominal*ratio*rng.uniform(.075,.12)*env*pinch*max(.22,1+wj*.28*math.sin(math.tau*2.2*q+phase))*heat
            pts.append((x,y)); ws.append(max(.001,width))
        # deterministic separated chunks
        gap1=.42+.05*(s%2); gap2=.70-.035*(s%3); chunks=[]; cp=[]; cw=[]
        for i,(pt,w) in enumerate(zip(pts,ws)):
            q=i/57.; gap=abs(q-gap1)<.030 or (s%2==0 and abs(q-gap2)<.022)
            if gap:
                if len(cp)>=3: chunks.append((cp,cw))
                cp=[]; cw=[]
            else: cp.append(pt); cw.append(w)
        if len(cp)>=3: chunks.append((cp,cw))
        for ci,(pp,ww) in enumerate(chunks):
            base.add_curve(f"{prefix}_core_support_{s}_{ci}",pp,[w*2.25 for w in ww],materials["inner_glow"],layers["PLASMA"],z=.57,frame=index+1,frames=frames)
            base.add_curve(f"{prefix}_core_hot_{s}_{ci}",pp,ww,materials["core"],layers["CORE"],z=.65,frame=index+1,frames=frames)


def add_bolder_tongues(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup):
    if breakup>.55: return
    nominal=float(p["thickness"])*float(p["shape.body_scale"]); count=max(10,int(p["shape.tongue_count"])); ctl=float(p["shape.tongue_length"]); curve=float(p["shape.tongue_curve"])
    # Only a subset is strongly visible; the rest are hairline texture.
    for s in range(count):
        rng=random.Random(seed*170003+s*5101+index*971); local=rng.uniform(.03,.97); u=tail+(head-tail)*local; x,y,a=v16.point_on_spine(radius,u,p); nx,ny=math.cos(a),math.sin(a); tx,ty=-math.sin(a),math.cos(a)
        x+=nx*nominal*rng.uniform(1.0,2.55); y+=ny*nominal*rng.uniform(1.0,2.55)
        sign=1 if rng.random()<.68 else -1; major=s in (1,6,13,21,30,36); length=radius*ctl*rng.uniform(.11,.29)*(1.0 if not major else rng.uniform(2.0,3.2))*(.65+.35*energy); phase=rng.uniform(0,math.tau); root=nominal*rng.uniform(.014,.035)*(2.0 if major else 1.0)
        pts=[]; ws=[]
        for i in range(16):
            q=i/15.; bend=math.sin(math.pi*q)*length*.13*curve*(-1 if s%3==0 else 1); flutter=math.sin(math.tau*1.8*q+phase)*length*.025*curve
            pts.append((x+tx*sign*length*q+nx*(bend+flutter),y+ty*sign*length*q+ny*(bend+flutter))); ws.append(max(.0008,root*(math.sin(math.pi*q)**.38)*(1-.55*q)))
        mat=materials["outer"] if s%3 else materials["body"]
        base.add_curve(f"{prefix}_edge_tongue_{s}",pts,ws,mat,layers["WISPS"],z=.43,frame=index+1,frames=frames)


def build_frame(spec,index,materials,layers):
    p=spec["params"]; v14._ACTIVE_PARAMS=p; radius=float(p["radius"]); frames=int(spec["frames"]); seed=int(spec["seed"]); tail,head,energy,breakup=v6.motion_window(index,frames,float(p["timing.peak"])); prefix=f"F{index+1:02d}"
    if index==0: v9.add_ignition(prefix,p,radius,materials,layers,seed,index,frames); return
    progress=base.dissolve_progress(p,index,frames,core=False); removed=[]
    if progress<=0:
        add_powered_mass(prefix,p,radius,tail,head,materials,layers,seed,index,frames)
        add_bolder_tongues(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
        add_core(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
        v14.add_hotspots(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
        v12.add_lightning(prefix,p,radius,tail,head,energy,breakup,materials,layers,seed,index,frames)
    else:
        # Late frames transition to real eroded meshes so transparent holes and islands exist in geometry.
        removed += v9.add_ribbon(prefix+"_erode_outer","body",p,radius,tail,head,materials["outer"],layers["BODY"],seed,index,frames,.08,2.55,.34,1.12)
        removed += v9.add_ribbon(prefix+"_erode_body","body",p,radius,tail,head,materials["body"],layers["BODY"],seed+31,index,frames,.14,1.55,.22,1.0)
        removed += v9.add_ribbon(prefix+"_erode_inner","inner",p,radius,tail,head,materials["inner"],layers["BODY"],seed+47,index,frames,.26,.18,.04,.62)
        v8.add_fragments(prefix,removed,p,materials,layers,radius,seed,index,frames,breakup)
        if index==frames-1: v13.add_terminal_shards(prefix,p,radius,tail,head,materials,layers,seed,index,frames)


def embed_sources(spec):
    v16.embed_sources(spec)
    try:
        t=bpy.data.texts.new("SOURCE_native_generate_vfx_v17.py"); t.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError: pass

v12.point_on_spine=v16.point_on_spine; v9.point_on_spine=v16.point_on_spine; v8.point_on_spine=v16.point_on_spine; v7.point_on_spine=v16.point_on_spine; base.point_on_arc=v16.point_on_spine
base.setup_scene=setup_scene; base.make_materials=v14.make_materials; base.build_frame=build_frame; base.embed_sources=embed_sources
if __name__=="__main__": base.main()
