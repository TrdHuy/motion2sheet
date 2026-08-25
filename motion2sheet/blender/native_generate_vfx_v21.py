"""Blender-native VFX renderer V21: outward integrated lightning roots."""
from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path

import bpy

_V20_PATH=Path(__file__).with_name("native_generate_vfx_v20.py")
_SPEC=importlib.util.spec_from_file_location("motion2sheet_native_vfx_v20",_V20_PATH)
if _SPEC is None or _SPEC.loader is None: raise RuntimeError("Unable to load V20")
v20=importlib.util.module_from_spec(_SPEC); _SPEC.loader.exec_module(v20)
v19,v18,v17,v16,v15,v14,v13,v12,v9,v8,v7,v6,base=v20.v19,v20.v18,v20.v17,v20.v16,v20.v15,v20.v14,v20.v13,v20.v12,v20.v9,v20.v8,v20.v7,v20.v6,v20.base


def setup_scene(spec):
    scene,layers=v20.setup_scene(spec)
    scene["vfx_renderer"]="blender-native-v21"
    scene["vfx_lightning_model"]="two-outward-major-bolts-with-hot-root-bridges"
    return scene,layers


def _major_path(p,radius,u,length,tangent_bias,jitter,rng):
    x,y,a=v16.point_on_spine(radius,u,p)
    nx,ny=math.cos(a),math.sin(a); tx,ty=-math.sin(a),math.cos(a)
    nominal=float(p["thickness"])*float(p["shape.body_scale"])
    # Start inside cyan/core region, then cross the outer shell and continue outside.
    root_offset=nominal*.30
    x+=nx*root_offset; y+=ny*root_offset
    phase=rng.uniform(0,math.tau); pts=[]; steps=19
    for i in range(steps):
        q=i/(steps-1)
        outward=length*q
        tangent=tangent_bias*length*(q**1.08)
        zig=(math.sin(math.tau*2.25*q+phase)+.36*math.sin(math.tau*5.1*q+phase*.43))*jitter*length*.085
        kick=rng.uniform(-1,1)*jitter*length*.014*(math.sin(math.pi*q)**.75)
        pts.append((x+nx*outward+tx*(tangent+zig+kick),y+ny*outward+ty*(tangent+zig+kick)))
    return pts,(nx,ny,tx,ty)


def add_lightning(prefix,p,radius,tail,head,energy,breakup,materials,layers,seed,index,frames):
    if energy<.48 or breakup>.72: return
    nominal=float(p["thickness"])*float(p["shape.body_scale"])
    count=max(2,int(p["lightning.major_count"])); jitter=float(p["lightning.jitter"]); length_ctl=float(p["lightning.length"])
    branch_p=float(p["lightning.branch_probability"]); depth=max(1,int(p["lightning.branch_depth"])); minor_ratio=float(p["lightning.minor_width_ratio"]); minor_len=float(p["lightning.minor_length_ratio"])
    anchors=(.27,.69); tangent_biases=(-.18,.16)
    for bi in range(count):
        rng=random.Random(seed*701003+index*10009+bi*811)
        local=anchors[bi%2]; u=tail+(head-tail)*local
        length=radius*length_ctl*rng.uniform(.38,.54)*(.70+.30*energy)
        pts,axes=_major_path(p,radius,u,length,tangent_biases[bi%2],jitter,rng)
        rootw=nominal*rng.uniform(.085,.125)
        ws=[]
        for i in range(len(pts)):
            q=i/(len(pts)-1)
            pulse=.88+.22*math.sin(math.tau*1.7*q+bi*.9)
            ws.append(max(.0012,rootw*((1-q)**1.28)*pulse))
        # Cyan root bridge visually ties the white bolt into the hot core instead of
        # making it look pasted onto or detached from the shell.
        bridge=pts[:5]
        bws=[rootw*1.85,rootw*1.65,rootw*1.35,rootw*.95,rootw*.62]
        base.add_curve(f"{prefix}_major_root_glow_{bi}",bridge,[w*2.25 for w in bws],materials["core_glow"],layers["PLASMA"],z=.69,frame=index+1,frames=frames)
        base.add_curve(f"{prefix}_major_root_cyan_{bi}",bridge,bws,materials["inner"],layers["CORE"],z=.72,frame=index+1,frames=frames)
        base.add_curve(f"{prefix}_major_glow_{bi}",pts,[w*2.0 for w in ws],materials["lightning_glow"],layers["PLASMA"],z=.73,frame=index+1,frames=frames)
        base.add_curve(f"{prefix}_major_{bi}",pts,ws,materials["lightning"],layers["LIGHTNING"],z=.77,frame=index+1,frames=frames)
        # One or two branches, always after the bolt has crossed the shell.
        if depth>0 and rng.random()<branch_p+.28:
            for level in range(min(depth,2)):
                si=min(len(pts)-4,8+level*3+rng.randint(-1,1))
                bx,by=pts[si]; px0,py0=pts[si-1]
                dx,dy=bx-px0,by-py0; dl=max(1e-6,math.hypot(dx,dy)); dx/=dl; dy/=dl; px,py=-dy,dx
                bl=length*minor_len*(.66**level)*rng.uniform(.40,.66); sign=-1 if (bi+level)%2 else 1
                bpts=[]
                for j in range(10):
                    q=j/9.; bend=sign*math.sin(math.pi*q)*bl*.25
                    bpts.append((bx+dx*bl*q+px*bend,by+dy*bl*q+py*bend))
                bw=rootw*minor_ratio*(.70**level); bws2=[max(.0010,bw*((1-j/9.)**1.18)) for j in range(10)]
                base.add_curve(f"{prefix}_branch_glow_{bi}_{level}",bpts,[w*1.6 for w in bws2],materials["lightning_glow"],layers["PLASMA"],z=.74,frame=index+1,frames=frames)
                base.add_curve(f"{prefix}_branch_{bi}_{level}",bpts,bws2,materials["lightning"],layers["LIGHTNING"],z=.78,frame=index+1,frames=frames)
    # Keep micro-cracks surface-bound and subtle.
    micro=max(int(p["lightning.surface_crack_count"]),int(p["lightning.micro_count"])); micro=round(micro*(1 if breakup<.34 else max(.22,1-(breakup-.34)*1.5)))
    for mi in range(micro):
        rng=random.Random(seed*99103+index*4099+mi*317); local=rng.uniform(.12,.90); u=tail+(head-tail)*local
        x,y,a=v16.point_on_spine(radius,u,p); nx,ny=math.cos(a),math.sin(a); tx,ty=-math.sin(a),math.cos(a)
        x+=nx*nominal*rng.uniform(.38,1.05); y+=ny*nominal*rng.uniform(.38,1.05)
        ln=radius*rng.uniform(.022,.052)*length_ctl; sign=-1 if rng.random()<.5 else 1
        pts=[(x,y),(x+tx*ln*.48+nx*sign*ln*.08,y+ty*ln*.48+ny*sign*ln*.08),(x+tx*ln,y+ty*ln)]
        w=nominal*.0078
        base.add_curve(f"{prefix}_micro_{mi}",pts,[w,w*.62,.001],materials["lightning"],layers["LIGHTNING"],z=.735,frame=index+1,frames=frames)


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
        v17.add_powered_mass(prefix,p,radius,tail,head,materials,layers,seed,index,frames)
        v19.add_directional_tongues(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
        v18.add_core(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
        add_lightning(prefix,p,radius,tail,head,energy,breakup,materials,layers,seed,index,frames)
        return
    removed=[]
    removed+=v9.add_ribbon(prefix+"_erode_outer","body",p,radius,tail,head,materials["outer"],layers["BODY"],seed,index,frames,.08,2.55,.34,1.12)
    removed+=v9.add_ribbon(prefix+"_erode_body","body",p,radius,tail,head,materials["body"],layers["BODY"],seed+31,index,frames,.14,1.55,.22,1.0)
    removed+=v9.add_ribbon(prefix+"_erode_inner","inner",p,radius,tail,head,materials["inner"],layers["BODY"],seed+47,index,frames,.26,.18,.04,.62)
    v8.add_fragments(prefix,removed,p,materials,layers,radius,seed,index,frames,breakup)
    if index==frames-1: v13.add_terminal_shards(prefix,p,radius,tail,head,materials,layers,seed,index,frames)


def embed_sources(spec):
    v20.embed_sources(spec)
    try:
        t=bpy.data.texts.new("SOURCE_native_generate_vfx_v21.py"); t.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError: pass

v17._band_polygon=v19._band_polygon
v12.point_on_spine=v16.point_on_spine; v9.point_on_spine=v16.point_on_spine; v8.point_on_spine=v16.point_on_spine; v7.point_on_spine=v16.point_on_spine; base.point_on_arc=v16.point_on_spine
base.setup_scene=setup_scene; base.make_materials=v14.make_materials; base.build_frame=build_frame; base.embed_sources=embed_sources
if __name__=="__main__": base.main()
