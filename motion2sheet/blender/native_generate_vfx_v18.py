"""Blender-native VFX renderer V18: stronger hot core + coherent late baseline."""
from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path

import bpy

_V17_PATH = Path(__file__).with_name("native_generate_vfx_v17.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v17", _V17_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load V17")
v17 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v17)
v16,v15,v14,v13,v12,v9,v8,v7,v6,base = v17.v16,v17.v15,v17.v14,v17.v13,v17.v12,v17.v9,v17.v8,v17.v7,v17.v6,v17.base


def setup_scene(spec):
    scene,layers=v17.setup_scene(spec)
    scene["vfx_renderer"]="blender-native-v18"
    scene["vfx_core_model"]="five-segmented-white-hot-streaks"
    scene["vfx_late_baseline"]="coherent-connected-ribbons"
    scene["vfx_f6_transition"]="powered-hold-before-breakup"
    return scene,layers


def _band_polygon(p,radius,tail,head,outer_scale,inner_scale,seed,phase_shift=0.0):
    """V17 coherent band with stronger contract edge/detail modulation."""
    rng=random.Random(seed); phase=rng.uniform(0,math.tau)+phase_shift
    nominal=float(p["thickness"])*float(p["shape.body_scale"])
    outer=[]; inner=[]; samples=112
    edge=float(p["shape.edge_noise"]); ef=float(p["shape.edge_noise_frequency"])
    detail=float(p["shape.detail_noise"]); df=float(p["shape.detail_noise_frequency"])
    taper=max(.18,float(p["shape.taper_power"])); flare=float(p["shape.flare"])
    for i in range(samples):
        q=i/(samples-1); u=tail+(head-tail)*q
        x,y,a=v16.point_on_spine(radius,u,p); nx,ny=math.cos(a),math.sin(a); tx,ty=-math.sin(a),math.cos(a)
        env=math.sin(math.pi*q)**taper
        belly=math.exp(-((q-.55)/.25)**2); shoulder=math.exp(-((q-.23)/.15)**2); lower=math.exp(-((q-.79)/.16)**2)
        macro=(.62+(1.00+.35*flare)*belly+.28*shoulder+.36*lower)*(.48+.52*env)
        # Two octaves at contract-driven frequencies plus sparse localized tears.
        coarse=math.sin(math.tau*(ef*.078)*q+phase)+.48*math.sin(math.tau*(ef*.039)*q+phase*.53)
        fine=math.sin(math.tau*(df*.060)*q+phase*.37)+.34*math.sin(math.tau*(df*.112)*q+phase*.81)
        notch=0.0
        for center,width,depth in ((.17,.035,.10),(.37,.050,.15),(.63,.042,.12),(.83,.032,.09)):
            notch -= depth*math.exp(-((q-center)/width)**2)
        spike=.10*math.exp(-((q-.29)/.030)**2)+.12*math.exp(-((q-.72)/.040)**2)
        ow=nominal*outer_scale*macro*(1+edge*.070*coarse+detail*.040*fine+notch+spike)
        iw=nominal*inner_scale*(.50+.19*belly)*(.43+.57*env)*(1+edge*.018*coarse-detail*.012*fine)
        shift=nominal*(.085*math.sin(math.tau*1.32*q+phase)+.030*math.sin(math.tau*3.1*q+phase*.43))
        cx=x+nx*shift+tx*nominal*.023*math.sin(math.tau*1.1*q+phase)
        cy=y+ny*shift+ty*nominal*.023*math.sin(math.tau*1.1*q+phase)
        outer.append((cx+nx*max(nominal*.08,ow),cy+ny*max(nominal*.08,ow)))
        inner.append((cx-nx*max(nominal*.04,iw),cy-ny*max(nominal*.04,iw)))
    return outer+list(reversed(inner))


def add_core(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup):
    """Five thick but broken white-hot streaks with cyan energy support."""
    heat=base.smoothstep((energy-.48)/.52)
    if heat<.02 or breakup>.68:
        return
    count=max(3,int(p["core.streak_count"]))
    nominal=float(p["thickness"])*float(p["shape.body_scale"])
    ratio=float(p["core.streak_width_ratio"])
    wj=float(p["core.width_jitter"])
    split=float(p["core.split_probability"])
    center_jitter=float(p["core.center_jitter"])/max(1.0,float(p["core.width_max"]))
    for s in range(count):
        rng=random.Random(seed*760001+s*9209+index*3571)
        start=rng.uniform(.04,.22); end=rng.uniform(.72,.96)
        lane=.30+.105*s+rng.uniform(-.055,.055)
        phase=rng.uniform(0,math.tau); freq=rng.uniform(1.15,2.35)
        pts=[]; ws=[]
        for i in range(86):
            q=i/85.; local=start+(end-start)*q
            x,y,a=v16.point_on_spine(radius,tail+(head-tail)*local,p)
            nx,ny=math.cos(a),math.sin(a); tx,ty=-math.sin(a),math.cos(a)
            off=lane+center_jitter*(.50*math.sin(math.tau*freq*q+phase)+.18*math.sin(math.tau*3.2*q+phase*.41))
            x+=nx*nominal*off+tx*nominal*.060*math.sin(math.tau*2.25*q+phase)
            y+=ny*nominal*off+ty*nominal*.060*math.sin(math.tau*2.25*q+phase)
            env=math.sin(math.pi*q)**.32
            # Thick islands separated by strong pinches so white never becomes a slab.
            pinch=1.0
            for pc in (.23+.015*s,.48-.010*s,.70+.012*s):
                d=abs(q-pc)
                if d<.052: pinch*=.11+.89*d/.052
            pulse=.78+.30*math.sin(math.tau*(1.65+.11*s)*q+phase)
            width=nominal*ratio*rng.uniform(.17,.25)*env*pinch*max(.25,1+wj*.34*math.sin(math.tau*2.2*q+phase))*heat*pulse
            pts.append((x,y)); ws.append(max(.0012,width))
        gaps=[.31+.025*(s%2), .58-.018*(s%3)]
        if rng.random()<split+.42: gaps.append(.78-.012*s)
        chunks=[]; cp=[]; cw=[]
        for i,(pt,w) in enumerate(zip(pts,ws)):
            q=i/85.; gap=any(abs(q-g)<(.022+.007*(s%2)) for g in gaps)
            if gap:
                if len(cp)>=4: chunks.append((cp,cw))
                cp=[]; cw=[]
            else:
                cp.append(pt); cw.append(w)
        if len(cp)>=4: chunks.append((cp,cw))
        for ci,(pp,ww) in enumerate(chunks):
            base.add_curve(f"{prefix}_core_cyan_{s}_{ci}",pp,[w*3.10 for w in ww],materials["inner_glow"],layers["PLASMA"],z=.565,frame=index+1,frames=frames)
            base.add_curve(f"{prefix}_core_glow_{s}_{ci}",pp,[w*1.72 for w in ww],materials["core_glow"],layers["PLASMA"],z=.615,frame=index+1,frames=frames)
            base.add_curve(f"{prefix}_core_hot_{s}_{ci}",pp,ww,materials["core"],layers["CORE"],z=.67,frame=index+1,frames=frames)


def add_hotspots(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup):
    if energy<.60 or breakup>.55:
        return
    count=max(1,int(p["core.hotspot_count"]))
    scale=float(p["core.hotspot_scale"]); nominal=float(p["thickness"])*float(p["shape.body_scale"])
    for hi in range(count):
        rng=random.Random(seed*500009+hi*8101+index*353)
        local=(hi+1)/(count+1)+rng.uniform(-.045,.045)
        u=tail+(head-tail)*base.clamp01(local)
        x,y,a=v16.point_on_spine(radius,u,p); nx,ny=math.cos(a),math.sin(a); tx,ty=-math.sin(a),math.cos(a)
        x+=nx*nominal*rng.uniform(.18,.42); y+=ny*nominal*rng.uniform(.18,.42)
        tr=nominal*rng.uniform(.27,.42)*scale; nr=nominal*rng.uniform(.15,.25)*scale
        phase=rng.uniform(0,math.tau); loop=[]
        for k in range(24):
            aa=math.tau*k/24.; wobble=1+.18*math.sin(3*aa+phase)+.09*math.sin(5*aa+phase*.37)
            loop.append((x+tx*tr*wobble*math.cos(aa)+nx*nr*math.sin(aa),y+ty*tr*wobble*math.cos(aa)+ny*nr*math.sin(aa)))
        base.add_polygon(f"{prefix}_hotspot_glow_{hi}",loop,materials["core_glow"],layers["PLASMA"],z=.62,frame=index+1,frames=frames)
        inner=[(x+(px-x)*.60,y+(py-y)*.60) for px,py in loop]
        base.add_polygon(f"{prefix}_hotspot_{hi}",inner,materials["core"],layers["CORE"],z=.68,frame=index+1,frames=frames)


def add_coherent_late_baseline(prefix,p,radius,tail,head,materials,layers,seed,index,frames):
    """Late dissolve-off reference must be visually continuous, not already fragmented."""
    # One broad connected support is enough to make the baseline topology honest.
    v9.add_ribbon(prefix+"_baseline_support","body",p,radius,tail,head,materials["outer"],layers["BODY"],seed+211,index,frames,.08,2.35,.31,.55)
    v9.add_ribbon(prefix+"_baseline_body","body",p,radius,tail,head,materials["body"],layers["BODY"],seed+227,index,frames,.14,1.30,.17,.45)
    v9.add_ribbon(prefix+"_baseline_inner","inner",p,radius,tail,head,materials["inner"],layers["BODY"],seed+239,index,frames,.24,.12,.025,.30)


def build_frame(spec,index,materials,layers):
    p=spec["params"]; v14._ACTIVE_PARAMS=p
    radius=float(p["radius"]); frames=int(spec["frames"]); seed=int(spec["seed"])
    tail,head,energy,breakup=v6.motion_window(index,frames,float(p["timing.peak"])); prefix=f"F{index+1:02d}"
    if index==0:
        v9.add_ignition(prefix,p,radius,materials,layers,seed,index,frames); return
    progress=base.dissolve_progress(p,index,frames,core=False)
    strength=float(p["dissolve.strength"])

    if progress<=0:
        # F7/F8 in the dissolve-off reference use a connected late body. Earlier
        # frames retain the richer polygon powered phase used by active output.
        if strength<=0 and index>=frames-2:
            add_coherent_late_baseline(prefix,p,radius,tail,head,materials,layers,seed,index,frames)
            return
        v17.add_powered_mass(prefix,p,radius,tail,head,materials,layers,seed,index,frames)
        v17.add_bolder_tongues(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
        add_core(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
        add_hotspots(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
        v12.add_lightning(prefix,p,radius,tail,head,energy,breakup,materials,layers,seed,index,frames)
        return

    # F6 is intentionally a gentle pre-breakup frame.  The previous renderer
    # abruptly changed representation as soon as dissolve became non-zero.
    if index==frames-3 and progress<.28:
        v17.add_powered_mass(prefix,p,radius,tail,head,materials,layers,seed,index,frames)
        v17.add_bolder_tongues(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
        add_core(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
        return

    removed=[]
    removed += v9.add_ribbon(prefix+"_erode_outer","body",p,radius,tail,head,materials["outer"],layers["BODY"],seed,index,frames,.08,2.55,.34,1.12)
    removed += v9.add_ribbon(prefix+"_erode_body","body",p,radius,tail,head,materials["body"],layers["BODY"],seed+31,index,frames,.14,1.55,.22,1.0)
    removed += v9.add_ribbon(prefix+"_erode_inner","inner",p,radius,tail,head,materials["inner"],layers["BODY"],seed+47,index,frames,.26,.18,.04,.62)
    v8.add_fragments(prefix,removed,p,materials,layers,radius,seed,index,frames,breakup)
    if index==frames-1:
        v13.add_terminal_shards(prefix,p,radius,tail,head,materials,layers,seed,index,frames)


def embed_sources(spec):
    v17.embed_sources(spec)
    try:
        t=bpy.data.texts.new("SOURCE_native_generate_vfx_v18.py"); t.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError:
        pass

# V17 powered mass resolves its polygon builder dynamically in its own module.
v17._band_polygon=_band_polygon
v12.point_on_spine=v16.point_on_spine; v9.point_on_spine=v16.point_on_spine; v8.point_on_spine=v16.point_on_spine; v7.point_on_spine=v16.point_on_spine; base.point_on_arc=v16.point_on_spine
base.setup_scene=setup_scene; base.make_materials=v14.make_materials; base.build_frame=build_frame; base.embed_sources=embed_sources

if __name__=="__main__":
    base.main()
