"""Blender-native VFX renderer V16: open slash trajectory + coherent terminal support."""
from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path

import bpy

_V15_PATH = Path(__file__).with_name("native_generate_vfx_v15.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v15", _V15_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load Blender-native V15 renderer")
v15 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v15)
v14,v13,v12,v9,v8,v7,v6,base = v15.v14,v15.v13,v15.v12,v15.v9,v15.v8,v15.v7,v15.v6,v15.base

_CTRL=((1.15,1.06),(.57,1.03),(.06,.83),(-.25,.49),(-.23,.10),(.02,-.29),(.47,-.54),(1.18,-.61))


def _catmull(p0,p1,p2,p3,t):
    t2=t*t; t3=t2*t
    return (.5*((2*p1[0])+(-p0[0]+p2[0])*t+(2*p0[0]-5*p1[0]+4*p2[0]-p3[0])*t2+(-p0[0]+3*p1[0]-3*p2[0]+p3[0])*t3),
            .5*((2*p1[1])+(-p0[1]+p2[1])*t+(2*p0[1]-5*p1[1]+4*p2[1]-p3[1])*t2+(-p0[1]+3*p1[1]-3*p2[1]+p3[1])*t3))


def _raw_spine(radius,t,p):
    t=base.clamp01(t); n=len(_CTRL)-1; s=t*n; seg=min(n-1,int(s)); q=s-seg
    p1,p2=_CTRL[seg],_CTRL[seg+1]; p0=_CTRL[seg-1] if seg>0 else p1; p3=_CTRL[seg+2] if seg+2<len(_CTRL) else p2
    x,y=_catmull(p0,p1,p2,p3,q)
    form=float(p["shape.form_noise"]); ff=float(p["shape.form_noise_frequency"])
    # Independent low-frequency warps create a slash-like sweep rather than a circle arc.
    x += form*(.042*math.sin(math.tau*.43*ff*t+.22)+.016*math.sin(math.tau*.79*ff*t+1.10))
    y += form*(.030*math.sin(math.tau*.37*ff*t+.91)+.012*math.sin(math.tau*.73*ff*t+.35))
    rot=math.radians(float(p.get("rotation",0.0))); cr,sr=math.cos(rot),math.sin(rot)
    x,y=x*cr-y*sr,x*sr+y*cr
    x*=radius; y*=radius
    x+=float(p["shape.offset_x"])*radius*3.0; y-=float(p["shape.offset_y"])*radius*3.0
    return x,y


def point_on_spine(radius,t,p):
    x,y=_raw_spine(radius,t,p); e=.0015
    xa,ya=_raw_spine(radius,max(0,t-e),p); xb,yb=_raw_spine(radius,min(1,t+e),p)
    return x,y,math.atan2(yb-ya,xb-xa)-math.pi*.5


def setup_scene(spec):
    scene,layers=v15.setup_scene(spec)
    scene["vfx_renderer"]="blender-native-v16"
    scene["vfx_shape_model"]="open-asymmetric-slash"
    scene["vfx_terminal_support"]="baseline-connected-active-eroded"
    return scene,layers


def add_segmented_core(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup):
    heat=base.smoothstep((energy-.54)/.46)
    if heat<.02 or breakup>.67: return
    count=max(3,int(p["core.streak_count"])); nominal=float(p["thickness"])*float(p["shape.body_scale"])
    cj=float(p["core.center_jitter"])/max(1.0,float(p["core.width_max"])); wj=float(p["core.width_jitter"]); ratio=float(p["core.streak_width_ratio"]); split=float(p["core.split_probability"])
    for s in range(count):
        rng=random.Random(seed*700001+s*8191+index*3571)
        start=max(.03,.04+s*.048+rng.uniform(-.025,.025)); end=min(.97,start+rng.uniform(.40,.64))
        # Shift the hot streams into the plasma mass.  Negative lanes formed an inner white outline in V15.
        lane=.05+.105*s+rng.uniform(-.035,.035); phase=rng.uniform(0,math.tau); freq=rng.uniform(1.35,2.75)
        pts=[]; ws=[]
        for i in range(68):
            q=i/67.; local=start+(end-start)*q; x,y,a=point_on_spine(radius,tail+(head-tail)*local,p)
            nx,ny=math.cos(a),math.sin(a); tx,ty=-math.sin(a),math.cos(a)
            off=lane+cj*(.18*math.sin(math.tau*freq*q+phase)+.06*math.sin(math.tau*3.05*q+phase*.41))
            x+=nx*nominal*off+tx*nominal*.035*math.sin(math.tau*2.3*q+phase); y+=ny*nominal*off+ty*nominal*.035*math.sin(math.tau*2.3*q+phase)
            env=math.sin(math.pi*q)**.46; pinch=1.
            for pc in (.24+.035*s,.53-.02*s,.76):
                d=abs(q-pc)
                if d<.045: pinch*=.15+.85*d/.045
            jitter=max(.22,1+wj*.25*math.sin(math.tau*2.0*q+phase)); w=nominal*ratio*rng.uniform(.085,.125)*env*pinch*jitter*heat
            pts.append((x,y)); ws.append(max(.001,w))
        gaps=[rng.uniform(.28,.72)] + ([rng.uniform(.20,.82)] if rng.random()<split else [])
        chunks=[]; cp=[]; cw=[]
        for i,(pt,w) in enumerate(zip(pts,ws)):
            q=i/67.; gap=any(abs(q-g)<.026 for g in gaps)
            if gap:
                if len(cp)>=3: chunks.append((cp,cw))
                cp=[]; cw=[]
            else: cp.append(pt); cw.append(w)
        if len(cp)>=3: chunks.append((cp,cw))
        for ci,(cpts,cws) in enumerate(chunks):
            base.add_curve(f"{prefix}_core_cyan_{s}_{ci}",cpts,[w*2.15 for w in cws],materials["inner_glow"],layers["PLASMA"],z=.57,frame=index+1,frames=frames)
            base.add_curve(f"{prefix}_core_white_{s}_{ci}",cpts,cws,materials["core"],layers["CORE"],z=.64,frame=index+1,frames=frames)


def add_terminal_bridge(prefix,p,radius,tail,head,materials,layers,index,frames):
    """Connected non-dissolved F8 support; active F8 represents this support fully eroded."""
    pts=[]; ws=[]; nominal=float(p["thickness"])*float(p["shape.body_scale"])
    for i in range(90):
        q=i/89.; x,y,_=point_on_spine(radius,tail+(head-tail)*q,p)
        env=math.sin(math.pi*q)**.34
        width=nominal*(1.05+1.10*math.exp(-((q-.55)/.28)**2))*env
        pts.append((x,y)); ws.append(max(.004,width))
    base.add_curve(f"{prefix}_terminal_connected_support",pts,ws,materials["outer"],layers["BODY"],z=.055,frame=index+1,frames=frames)


def build_frame(spec,index,materials,layers):
    p=spec["params"]; v14._ACTIVE_PARAMS=p
    radius=float(p["radius"]); frames=int(spec["frames"]); seed=int(spec["seed"])
    tail,head,energy,breakup=v6.motion_window(index,frames,float(p["timing.peak"])); prefix=f"F{index+1:02d}"
    if index==0:
        v9.add_ignition(prefix,p,radius,materials,layers,seed,index,frames); return
    active=float(p["dissolve.strength"])>0.; final=index==frames-1; removed=[]
    # In the non-dissolved terminal state this bridge joins the powered body into one coherent mass.
    if final and not active: add_terminal_bridge(prefix,p,radius,tail,head,materials,layers,index,frames)
    removed += v9.add_ribbon(prefix+"_outer_glow","body",p,radius,tail,head,materials["outer_glow"],layers["PLASMA"],seed,index,frames,.02,3.00,.44,1.08)
    removed += v9.add_ribbon(prefix+"_outer","body",p,radius,tail,head,materials["outer"],layers["BODY"],seed+7,index,frames,.08,2.46,.30,1.07)
    removed += v9.add_ribbon(prefix+"_body","body",p,radius,tail,head,materials["body"],layers["BODY"],seed+31,index,frames,.14,1.43,.17,.93)
    removed += v9.add_ribbon(prefix+"_inner","inner",p,radius,tail,head,materials["inner"],layers["BODY"],seed+47,index,frames,.28,.15,.032,.54)
    if not final:
        v14.add_edge_tongues(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
        add_segmented_core(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
        v14.add_hotspots(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
        v12.add_lightning(prefix,p,radius,tail,head,energy,breakup,materials,layers,seed,index,frames)
    elif active:
        v13.add_terminal_shards(prefix,p,radius,tail,head,materials,layers,seed,index,frames)
    v8.add_fragments(prefix,removed,p,materials,layers,radius,seed,index,frames,breakup)


def embed_sources(spec):
    v15.embed_sources(spec)
    try:
        text=bpy.data.texts.new("SOURCE_native_generate_vfx_v16.py"); text.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError: pass

# Patch every reused geometry helper to the V16 trajectory.
v12.point_on_spine=point_on_spine; v9.point_on_spine=point_on_spine; v8.point_on_spine=point_on_spine; v7.point_on_spine=point_on_spine; base.point_on_arc=point_on_spine
base.setup_scene=setup_scene; base.make_materials=v14.make_materials; base.build_frame=build_frame; base.embed_sources=embed_sources

if __name__=="__main__": base.main()
