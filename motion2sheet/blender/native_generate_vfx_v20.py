"""Blender-native VFX renderer V20: integrated major lightning hierarchy."""
from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path

import bpy

_V19_PATH=Path(__file__).with_name("native_generate_vfx_v19.py")
_SPEC=importlib.util.spec_from_file_location("motion2sheet_native_vfx_v19",_V19_PATH)
if _SPEC is None or _SPEC.loader is None: raise RuntimeError("Unable to load V19")
v19=importlib.util.module_from_spec(_SPEC); _SPEC.loader.exec_module(v19)
v18,v17,v16,v15,v14,v13,v12,v9,v8,v7,v6,base=v19.v18,v19.v17,v19.v16,v19.v15,v19.v14,v19.v13,v19.v12,v19.v9,v19.v8,v19.v7,v19.v6,v19.base


def setup_scene(spec):
    scene,layers=v19.setup_scene(spec)
    scene["vfx_renderer"]="blender-native-v20"
    scene["vfx_lightning_model"]="two-rooted-major-bolts-with-depth-two-branches"
    return scene,layers


def _bolt_path(p,radius,u,length,side,jitter,rng):
    x,y,a=v16.point_on_spine(radius,u,p)
    nx,ny=math.cos(a),math.sin(a); tx,ty=-math.sin(a),math.cos(a)
    # Root sits inside cyan/core region then exits through shell.
    root_in=-.22*float(p["thickness"])*float(p["shape.body_scale"])
    x+=nx*root_in; y+=ny*root_in
    if side<0: nx,ny=-nx,-ny
    pts=[]; steps=16; phase=rng.uniform(0,math.tau)
    for i in range(steps):
        q=i/(steps-1)
        zig=(math.sin(math.tau*2.1*q+phase)+.42*math.sin(math.tau*4.6*q+phase*.41))*jitter*length*.11
        kick=rng.uniform(-1,1)*jitter*length*.022*(math.sin(math.pi*q)**.7)
        pts.append((x+nx*length*q+tx*(zig+kick),y+ny*length*q+ty*(zig+kick)))
    return pts


def add_lightning(prefix,p,radius,tail,head,energy,breakup,materials,layers,seed,index,frames):
    if energy<.48 or breakup>.72: return
    nominal=float(p["thickness"])*float(p["shape.body_scale"])
    major=max(2,int(p["lightning.major_count"])); jitter=float(p["lightning.jitter"]); length_ctl=float(p["lightning.length"])
    branch_p=float(p["lightning.branch_probability"]); depth=max(1,int(p["lightning.branch_depth"])); minor_ratio=float(p["lightning.minor_width_ratio"]); minor_len=float(p["lightning.minor_length_ratio"])
    anchors=(.31,.66)
    for bi in range(major):
        rng=random.Random(seed*701003+index*10009+bi*811)
        local=anchors[bi%2]; u=tail+(head-tail)*local; side=1 if bi%2==0 else -1
        length=radius*length_ctl*rng.uniform(.43,.62)*(.68+.32*energy)
        pts=_bolt_path(p,radius,u,length,side,jitter,rng)
        rootw=nominal*rng.uniform(.075,.115)
        ws=[]
        for i in range(len(pts)):
            q=i/(len(pts)-1); wob=.82+.30*math.sin(math.tau*1.8*q+rng.uniform(-.25,.25)); ws.append(max(.0012,rootw*((1-q)**1.35)*wob))
        base.add_curve(f"{prefix}_major_glow_{bi}",pts,[w*2.0 for w in ws],materials["lightning_glow"],layers["PLASMA"],z=.70,frame=index+1,frames=frames)
        base.add_curve(f"{prefix}_major_{bi}",pts,ws,materials["lightning"],layers["LIGHTNING"],z=.75,frame=index+1,frames=frames)
        if depth>0 and rng.random()<branch_p+.20:
            for level in range(min(depth,2)):
                si=min(len(pts)-3,5+level*3+rng.randint(-1,1)); bx,by=pts[si]; px0,py0=pts[si-1]; dx,dy=bx-px0,by-py0; dl=max(1e-6,math.hypot(dx,dy)); dx/=dl; dy/=dl; px,py=-dy,dx
                bl=length*minor_len*(.68**level)*rng.uniform(.48,.78); sign=-1 if (bi+level)%2 else 1
                bpts=[]
                for j in range(9):
                    q=j/8.; bend=sign*math.sin(math.pi*q)*bl*.22; bpts.append((bx+dx*bl*q+px*bend,by+dy*bl*q+py*bend))
                bw=rootw*minor_ratio*(.72**level); bws=[max(.0010,bw*((1-j/8.)**1.22)) for j in range(9)]
                base.add_curve(f"{prefix}_branch_{bi}_{level}",bpts,bws,materials["lightning"],layers["LIGHTNING"],z=.76,frame=index+1,frames=frames)
    # Surface cracks: short embedded cyan-white fissures, not external hair.
    micro=max(int(p["lightning.surface_crack_count"]),int(p["lightning.micro_count"])); micro=round(micro*(1 if breakup<.34 else max(.22,1-(breakup-.34)*1.5)))
    for mi in range(micro):
        rng=random.Random(seed*99103+index*4099+mi*317); local=rng.uniform(.12,.90); u=tail+(head-tail)*local
        x,y,a=v16.point_on_spine(radius,u,p); nx,ny=math.cos(a),math.sin(a); tx,ty=-math.sin(a),math.cos(a)
        x+=nx*nominal*rng.uniform(.18,.75); y+=ny*nominal*rng.uniform(.18,.75)
        ln=radius*rng.uniform(.030,.068)*length_ctl; sign=-1 if rng.random()<.5 else 1
        pts=[(x,y),(x+tx*ln*.45+nx*sign*ln*.10,y+ty*ln*.45+ny*sign*ln*.10),(x+tx*ln,y+ty*ln)]
        w=nominal*.0095
        base.add_curve(f"{prefix}_micro_{mi}",pts,[w,w*.65,.001],materials["lightning"],layers["LIGHTNING"],z=.72,frame=index+1,frames=frames)


def build_frame(spec,index,materials,layers):
    p=spec["params"]; v14._ACTIVE_PARAMS=p; radius=float(p["radius"]); frames=int(spec["frames"]); seed=int(spec["seed"])
    tail,head,energy,breakup=v6.motion_window(index,frames,float(p["timing.peak"])); prefix=f"F{index+1:02d}"
    if index==0: v9.add_ignition(prefix,p,radius,materials,layers,seed,index,frames); return
    progress=base.dissolve_progress(p,index,frames,core=False); strength=float(p["dissolve.strength"])
    if progress<=0:
        if strength<=0 and index>=frames-2: v18.add_coherent_late_baseline(prefix,p,radius,tail,head,materials,layers,seed,index,frames); return
        v17.add_powered_mass(prefix,p,radius,tail,head,materials,layers,seed,index,frames)
        v19.add_directional_tongues(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
        v18.add_core(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
        v18.add_hotspots(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
        add_lightning(prefix,p,radius,tail,head,energy,breakup,materials,layers,seed,index,frames)
        return
    if index==frames-3 and progress<.28:
        v17.add_powered_mass(prefix,p,radius,tail,head,materials,layers,seed,index,frames); v19.add_directional_tongues(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup); v18.add_core(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup); add_lightning(prefix,p,radius,tail,head,energy,breakup,materials,layers,seed,index,frames); return
    removed=[]
    removed+=v9.add_ribbon(prefix+"_erode_outer","body",p,radius,tail,head,materials["outer"],layers["BODY"],seed,index,frames,.08,2.55,.34,1.12)
    removed+=v9.add_ribbon(prefix+"_erode_body","body",p,radius,tail,head,materials["body"],layers["BODY"],seed+31,index,frames,.14,1.55,.22,1.0)
    removed+=v9.add_ribbon(prefix+"_erode_inner","inner",p,radius,tail,head,materials["inner"],layers["BODY"],seed+47,index,frames,.26,.18,.04,.62)
    v8.add_fragments(prefix,removed,p,materials,layers,radius,seed,index,frames,breakup)
    if index==frames-1: v13.add_terminal_shards(prefix,p,radius,tail,head,materials,layers,seed,index,frames)


def embed_sources(spec):
    v19.embed_sources(spec)
    try:
        t=bpy.data.texts.new("SOURCE_native_generate_vfx_v20.py"); t.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError: pass

v17._band_polygon=v19._band_polygon
v12.point_on_spine=v16.point_on_spine; v9.point_on_spine=v16.point_on_spine; v8.point_on_spine=v16.point_on_spine; v7.point_on_spine=v16.point_on_spine; base.point_on_arc=v16.point_on_spine
base.setup_scene=setup_scene; base.make_materials=v14.make_materials; base.build_frame=build_frame; base.embed_sources=embed_sources
if __name__=="__main__": base.main()
