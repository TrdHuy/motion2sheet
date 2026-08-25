"""Blender-native VFX renderer V19: torn plasma shell + directional tongues."""
from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path

import bpy

_V18_PATH=Path(__file__).with_name("native_generate_vfx_v18.py")
_SPEC=importlib.util.spec_from_file_location("motion2sheet_native_vfx_v18",_V18_PATH)
if _SPEC is None or _SPEC.loader is None: raise RuntimeError("Unable to load V18")
v18=importlib.util.module_from_spec(_SPEC); _SPEC.loader.exec_module(v18)
v17,v16,v15,v14,v13,v12,v9,v8,v7,v6,base=v18.v17,v18.v16,v18.v15,v18.v14,v18.v13,v18.v12,v18.v9,v18.v8,v18.v7,v18.v6,v18.base


def setup_scene(spec):
    scene,layers=v18.setup_scene(spec)
    scene["vfx_renderer"]="blender-native-v19"
    scene["vfx_shell_model"]="torn-asymmetric-contract-shell"
    scene["vfx_tongues"]="directional-major-minor-hierarchy"
    return scene,layers


def _band_polygon(p,radius,tail,head,outer_scale,inner_scale,seed,phase_shift=0.0):
    rng=random.Random(seed); phase=rng.uniform(0,math.tau)+phase_shift
    nominal=float(p["thickness"])*float(p["shape.body_scale"])
    outer=[]; inner=[]; samples=128
    edge=float(p["shape.edge_noise"]); ef=float(p["shape.edge_noise_frequency"])
    detail=float(p["shape.detail_noise"]); df=float(p["shape.detail_noise_frequency"])
    taper=max(.18,float(p["shape.taper_power"])); flare=float(p["shape.flare"])
    # Layer-specific tear maps. They are smooth enough to stay painterly, but
    # large enough to break the synthetic C silhouette.
    tears=[(.12,.026,.18),(.24,.040,-.13),(.41,.032,.21),(.57,.050,-.17),(.73,.033,.22),(.88,.026,-.15)]
    spikes=[(.18,.025,.18),(.34,.030,.14),(.66,.034,.20),(.82,.024,.16)]
    for i in range(samples):
        q=i/(samples-1); u=tail+(head-tail)*q
        x,y,a=v16.point_on_spine(radius,u,p); nx,ny=math.cos(a),math.sin(a); tx,ty=-math.sin(a),math.cos(a)
        env=math.sin(math.pi*q)**taper
        belly=math.exp(-((q-.55)/.25)**2); shoulder=math.exp(-((q-.23)/.15)**2); lower=math.exp(-((q-.79)/.16)**2)
        macro=(.60+(1.00+.38*flare)*belly+.30*shoulder+.38*lower)*(.45+.55*env)
        coarse=math.sin(math.tau*(ef*.078)*q+phase)+.52*math.sin(math.tau*(ef*.039)*q+phase*.53)
        medium=math.sin(math.tau*(ef*.155)*q+phase*.73)
        fine=math.sin(math.tau*(df*.060)*q+phase*.37)+.38*math.sin(math.tau*(df*.112)*q+phase*.81)
        local=0.0
        for c,w,d in tears: local += d*math.exp(-((q-c)/w)**2)
        for c,w,d in spikes: local += d*math.exp(-((q-c)/w)**2)
        # Stronger contour modulation on outer edge than inner edge.
        outer_mod=1+edge*(.080*coarse+.022*medium)+detail*.050*fine+local
        inner_mod=1+edge*(.020*coarse+.008*medium)-detail*.014*fine-local*.10
        ow=nominal*outer_scale*macro*max(.28,outer_mod)
        iw=nominal*inner_scale*(.48+.20*belly)*(.40+.60*env)*max(.32,inner_mod)
        # Directional center drift plus local lateral kicks make the mass asymmetric.
        kick=.11*math.exp(-((q-.30)/.055)**2)-.09*math.exp(-((q-.64)/.065)**2)
        shift=nominal*(.095*math.sin(math.tau*1.25*q+phase)+.035*math.sin(math.tau*3.0*q+phase*.43)+kick)
        cx=x+nx*shift+tx*nominal*.028*math.sin(math.tau*1.08*q+phase)
        cy=y+ny*shift+ty*nominal*.028*math.sin(math.tau*1.08*q+phase)
        outer.append((cx+nx*max(nominal*.08,ow),cy+ny*max(nominal*.08,ow)))
        inner.append((cx-nx*max(nominal*.04,iw),cy-ny*max(nominal*.04,iw)))
    return outer+list(reversed(inner))


def add_directional_tongues(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup):
    if breakup>.52: return
    nominal=float(p["thickness"])*float(p["shape.body_scale"])
    count=max(12,int(p["shape.tongue_count"])); ctl=float(p["shape.tongue_length"]); curve=float(p["shape.tongue_curve"]); widthctl=float(p["shape.tongue_width"])
    # Six purposeful long tongues, the remainder are short torn edge accents.
    majors={2,7,13,20,28,35}
    for s in range(count):
        rng=random.Random(seed*190001+s*5147+index*977)
        # Favor top shoulder and lower exit, which gives the slash two clear directional tips.
        if s%3==0: local=rng.uniform(.10,.34)
        elif s%3==1: local=rng.uniform(.68,.94)
        else: local=rng.uniform(.34,.68)
        u=tail+(head-tail)*local; x,y,a=v16.point_on_spine(radius,u,p)
        nx,ny=math.cos(a),math.sin(a); tx,ty=-math.sin(a),math.cos(a)
        side=1 if rng.random()<.82 else -1
        x+=nx*nominal*(rng.uniform(1.45,2.85) if side>0 else rng.uniform(-.28,-.08))
        y+=ny*nominal*(rng.uniform(1.45,2.85) if side>0 else rng.uniform(-.28,-.08))
        major=s in majors
        sign=1 if (local>.52) else -1
        if rng.random()<.22: sign*=-1
        length=radius*ctl*rng.uniform(.10,.25)*(rng.uniform(2.3,3.6) if major else 1.0)*(.62+.38*energy)
        root=nominal*rng.uniform(.018,.040)*(.80+.65*widthctl)*(2.1 if major else 1.0)
        phase=rng.uniform(0,math.tau); pts=[]; ws=[]
        for i in range(18):
            q=i/17.; bend=(-1 if s%2 else 1)*math.sin(math.pi*q)*length*.14*curve
            flutter=math.sin(math.tau*(1.6+.2*(s%3))*q+phase)*length*.024*curve
            pts.append((x+tx*sign*length*q+nx*(bend+flutter),y+ty*sign*length*q+ny*(bend+flutter)))
            env=math.sin(math.pi*q)**.34; ws.append(max(.0008,root*env*(1-.60*q)))
        mat=materials["outer"] if s%3 else materials["body"]
        if major:
            glow=materials["outer_glow"] if mat==materials["outer"] else materials["body_glow"]
            base.add_curve(f"{prefix}_tongue_glow_{s}",pts,[w*1.55 for w in ws],glow,layers["PLASMA"],z=.39,frame=index+1,frames=frames)
        base.add_curve(f"{prefix}_tongue_{s}",pts,ws,mat,layers["WISPS"],z=.46,frame=index+1,frames=frames)


def build_frame(spec,index,materials,layers):
    p=spec["params"]; v14._ACTIVE_PARAMS=p
    radius=float(p["radius"]); frames=int(spec["frames"]); seed=int(spec["seed"])
    tail,head,energy,breakup=v6.motion_window(index,frames,float(p["timing.peak"])); prefix=f"F{index+1:02d}"
    if index==0: v9.add_ignition(prefix,p,radius,materials,layers,seed,index,frames); return
    progress=base.dissolve_progress(p,index,frames,core=False); strength=float(p["dissolve.strength"])
    if progress<=0:
        if strength<=0 and index>=frames-2:
            v18.add_coherent_late_baseline(prefix,p,radius,tail,head,materials,layers,seed,index,frames); return
        # Reuse V17 powered masses but patch their polygon builder to this V19 shell.
        v17.add_powered_mass(prefix,p,radius,tail,head,materials,layers,seed,index,frames)
        add_directional_tongues(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
        v18.add_core(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
        v18.add_hotspots(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
        v12.add_lightning(prefix,p,radius,tail,head,energy,breakup,materials,layers,seed,index,frames)
        return
    if index==frames-3 and progress<.28:
        v17.add_powered_mass(prefix,p,radius,tail,head,materials,layers,seed,index,frames)
        add_directional_tongues(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
        v18.add_core(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
        return
    removed=[]
    removed+=v9.add_ribbon(prefix+"_erode_outer","body",p,radius,tail,head,materials["outer"],layers["BODY"],seed,index,frames,.08,2.55,.34,1.12)
    removed+=v9.add_ribbon(prefix+"_erode_body","body",p,radius,tail,head,materials["body"],layers["BODY"],seed+31,index,frames,.14,1.55,.22,1.0)
    removed+=v9.add_ribbon(prefix+"_erode_inner","inner",p,radius,tail,head,materials["inner"],layers["BODY"],seed+47,index,frames,.26,.18,.04,.62)
    v8.add_fragments(prefix,removed,p,materials,layers,radius,seed,index,frames,breakup)
    if index==frames-1: v13.add_terminal_shards(prefix,p,radius,tail,head,materials,layers,seed,index,frames)


def embed_sources(spec):
    v18.embed_sources(spec)
    try:
        t=bpy.data.texts.new("SOURCE_native_generate_vfx_v19.py"); t.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError: pass

v17._band_polygon=_band_polygon
v12.point_on_spine=v16.point_on_spine; v9.point_on_spine=v16.point_on_spine; v8.point_on_spine=v16.point_on_spine; v7.point_on_spine=v16.point_on_spine; base.point_on_arc=v16.point_on_spine
base.setup_scene=setup_scene; base.make_materials=v14.make_materials; base.build_frame=build_frame; base.embed_sources=embed_sources
if __name__=="__main__": base.main()
