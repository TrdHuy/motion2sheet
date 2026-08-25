"""Blender-native VFX renderer V27: anchored buildup, thicker hot core, richer lightning, organic F6 cavities."""
from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path

import bpy

_V26_PATH = Path(__file__).with_name("native_generate_vfx_v26.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v26", _V26_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load V26")
v26 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v26)

v25, v24, v23 = v26.v25, v26.v24, v26.v23
v22, v21, v20, v19, v18, v17 = v23.v22, v23.v21, v23.v20, v23.v19, v23.v18, v23.v17
v16, v15, v14, v13, v12 = v23.v16, v23.v15, v23.v14, v23.v13, v23.v12
v9, v8, v7, v6, base = v23.v9, v23.v8, v23.v7, v23.v6, v23.base

_ORIG_MOTION_WINDOW = v6.motion_window
_ORIG_TRI_VIS = v23._ORIG_TRI_VIS


def setup_scene(spec):
    scene, layers = v23.setup_scene(spec)
    scene["vfx_renderer"] = "blender-native-v27"
    scene["vfx_buildup_model"] = "shared-anchor-reverse-growth"
    scene["vfx_f1_f2_continuity"] = "shared-spine-anchor-u055"
    scene["vfx_core_model"] = "thick-irregular-multistreak-hot-core"
    scene["vfx_lightning_model"] = "four-scale-varied-major-bolts-plus-micro-cracks"
    scene["vfx_f6_transition"] = "sparse-local-organic-cavities"
    return scene, layers


def motion_window(index: int, frames: int, peak_t: float):
    if frames == 8:
        if index == 1: return .55, .06, .70, 0.0
        if index == 2: return .72, .035, .84, 0.0
        if index == 3: return .88, .018, .95, 0.0
        if index == 4: return .98, .005, 1.00, 0.0
    return _ORIG_MOTION_WINDOW(index, frames, peak_t)


def _loop(cx, cy, rx, ry, points, phase, wobble=.12):
    out=[]
    for i in range(points):
        a=math.tau*i/points
        w=1.0+wobble*math.sin(3*a+phase)+wobble*.55*math.sin(5*a+phase*.47)
        out.append((cx+math.cos(a)*rx*w,cy+math.sin(a)*ry*w))
    return out


def add_ignition(prefix,p,radius,materials,layers,seed,index,frames):
    nominal=float(p["thickness"])*float(p["shape.body_scale"])
    x,y,_=v16.point_on_spine(radius,.55,p)
    rng=random.Random(seed*1301081+97); phase=rng.uniform(0,math.tau)
    rings=((nominal*1.42,nominal*.92,materials["outer_glow"],layers["PLASMA"],.20),
           (nominal*1.08,nominal*.70,materials["outer"],layers["BODY"],.27),
           (nominal*.82,nominal*.54,materials["body"],layers["BODY"],.34),
           (nominal*.56,nominal*.38,materials["inner"],layers["CORE"],.48),
           (nominal*.34,nominal*.25,materials["core"],layers["CORE"],.66))
    for li,(rx,ry,mat,coll,z) in enumerate(rings):
        base.add_polygon(f"{prefix}_ignition_ring_{li}",_loop(x,y,rx,ry,30,phase+li*.63,.16 if li<3 else .11),mat,coll,z=z,frame=index+1,frames=frames)
    for ri in range(12):
        rr=random.Random(seed*911382323+ri*10007); ang=rr.uniform(0,math.tau)
        length=radius*rr.uniform(.15,.62)*(1.0 if ri<7 else .72); start=nominal*rr.uniform(.22,.48); bend=rr.uniform(-.20,.20)
        pts=[]; steps=5 if ri<7 else 3
        for si in range(steps):
            q=si/max(1,steps-1); aa=ang+bend*math.sin(math.pi*q)+rr.uniform(-.045,.045)*(math.sin(math.pi*q)**.8); d=start+length*q
            pts.append((x+math.cos(aa)*d,y+math.sin(aa)*d))
        rootw=nominal*rr.uniform(.018,.065); ws=[max(.001,rootw*((1-si/max(1,steps-1))**1.25)) for si in range(steps)]
        base.add_curve(f"{prefix}_ignition_ray_glow_{ri}",pts,[w*2.0 for w in ws],materials["lightning_glow"],layers["PLASMA"],z=.70,frame=index+1,frames=frames)
        base.add_curve(f"{prefix}_ignition_ray_{ri}",pts,ws,materials["lightning"],layers["LIGHTNING"],z=.76,frame=index+1,frames=frames)
    for bi in range(5):
        rr=random.Random(seed*700001+bi*7919); ang=rr.uniform(0,math.tau); length=radius*rr.uniform(.25,.55); pts=[(x,y)]
        for si in range(1,8):
            q=si/7.; perp=rr.uniform(-1,1)*length*.055*math.sin(math.pi*q); dx,dy=math.cos(ang),math.sin(ang); px,py=-dy,dx
            pts.append((x+dx*length*q+px*perp,y+dy*length*q+py*perp))
        rootw=nominal*rr.uniform(.030,.095); ws=[max(.0012,rootw*((1-i/7.)**1.35)) for i in range(8)]
        base.add_curve(f"{prefix}_ignition_bolt_glow_{bi}",pts,[w*2.2 for w in ws],materials["lightning_glow"],layers["PLASMA"],z=.72,frame=index+1,frames=frames)
        base.add_curve(f"{prefix}_ignition_bolt_{bi}",pts,ws,materials["lightning"],layers["LIGHTNING"],z=.79,frame=index+1,frames=frames)


def add_core(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup):
    heat=base.smoothstep((energy-.40)/.60)
    if heat<.02 or breakup>.70: return
    count=max(4,int(p["core.streak_count"])); nominal=float(p["thickness"])*float(p["shape.body_scale"])
    ratio=float(p["core.streak_width_ratio"]); wj=float(p["core.width_jitter"]); split=float(p["core.split_probability"])
    center_jitter=float(p["core.center_jitter"])/max(1.0,float(p["core.width_max"]))
    for s in range(count):
        rng=random.Random(seed*760001+s*9209+index*3571); start=rng.uniform(.025,.13); end=rng.uniform(.82,.985); lane=.22+.095*s+rng.uniform(-.050,.050); phase=rng.uniform(0,math.tau); freq=rng.uniform(1.20,2.55)
        points=[]; widths=[]
        for i in range(92):
            q=i/91.; local=start+(end-start)*q; x,y,a=v16.point_on_spine(radius,tail+(head-tail)*local,p); nx,ny=math.cos(a),math.sin(a); tx,ty=-math.sin(a),math.cos(a)
            off=lane+center_jitter*(.52*math.sin(math.tau*freq*q+phase)+.19*math.sin(math.tau*3.2*q+phase*.41)); x+=nx*nominal*off+tx*nominal*.055*math.sin(math.tau*2.25*q+phase); y+=ny*nominal*off+ty*nominal*.055*math.sin(math.tau*2.25*q+phase)
            env=math.sin(math.pi*q)**.28; pinch=1.0
            for pc in (.22+.012*s,.47-.008*s,.69+.010*s):
                d=abs(q-pc)
                if d<.046: pinch*=.22+.78*d/.046
            pulse=.83+.23*math.sin(math.tau*(1.55+.10*s)*q+phase)+.10*math.sin(math.tau*4.2*q+phase*.37)
            width=nominal*ratio*rng.uniform(.43,.66)*env*pinch*max(.34,1+wj*.28*math.sin(math.tau*2.2*q+phase))*heat*pulse
            points.append((x,y)); widths.append(max(.0018,width))
        gaps=[.30+.022*(s%2),.56-.016*(s%3)]
        if rng.random()<split+.30: gaps.append(.77-.010*s)
        chunks=[]; cp=[]; cw=[]
        for i,(pt,w) in enumerate(zip(points,widths)):
            q=i/91.; gap=any(abs(q-g)<(.014+.005*(s%2)) for g in gaps)
            if gap:
                if len(cp)>=4: chunks.append((cp,cw))
                cp=[]; cw=[]
            else: cp.append(pt); cw.append(w)
        if len(cp)>=4: chunks.append((cp,cw))
        for ci,(pp,ww) in enumerate(chunks):
            base.add_curve(f"{prefix}_core_cyan_{s}_{ci}",pp,[w*2.35 for w in ww],materials["inner_glow"],layers["PLASMA"],z=.565,frame=index+1,frames=frames)
            base.add_curve(f"{prefix}_core_glow_{s}_{ci}",pp,[w*1.42 for w in ww],materials["core_glow"],layers["PLASMA"],z=.615,frame=index+1,frames=frames)
            base.add_curve(f"{prefix}_core_hot_{s}_{ci}",pp,ww,materials["core"],layers["CORE"],z=.67,frame=index+1,frames=frames)


def _bolt_path(p,radius,u,length,tangent_bias,jitter,rng):
    x,y,a=v16.point_on_spine(radius,u,p); nx,ny=math.cos(a),math.sin(a); tx,ty=-math.sin(a),math.cos(a); nominal=float(p["thickness"])*float(p["shape.body_scale"]); x+=nx*nominal*.28; y+=ny*nominal*.28
    phase=rng.uniform(0,math.tau); pts=[]; steps=rng.randint(14,23); f1=rng.uniform(1.7,2.7); f2=rng.uniform(4.2,6.2)
    for i in range(steps):
        q=i/(steps-1); outward=length*q; tangent=tangent_bias*length*(q**1.05); zig=(math.sin(math.tau*f1*q+phase)+.34*math.sin(math.tau*f2*q+phase*.43))*jitter*length*.080; kick=rng.uniform(-1,1)*jitter*length*.018*(math.sin(math.pi*q)**.8)
        pts.append((x+nx*outward+tx*(tangent+zig+kick),y+ny*outward+ty*(tangent+zig+kick)))
    return pts


def add_lightning(prefix,p,radius,tail,head,energy,breakup,materials,layers,seed,index,frames):
    if energy<.40 or breakup>.74: return
    nominal=float(p["thickness"])*float(p["shape.body_scale"]); requested=int(p["lightning.major_count"]); count=max(4,requested+2); jitter=float(p["lightning.jitter"]); length_ctl=float(p["lightning.length"]); branch_p=float(p["lightning.branch_probability"]); depth=max(1,int(p["lightning.branch_depth"])); minor_ratio=float(p["lightning.minor_width_ratio"]); minor_len=float(p["lightning.minor_length_ratio"])
    anchor_rng=random.Random(seed*19491001+index*1907); anchors=sorted(anchor_rng.uniform(.14,.86) for _ in range(count))
    for bi,local in enumerate(anchors):
        rng=random.Random(seed*701003+index*10009+bi*811); u=tail+(head-tail)*local
        if bi<2: lf=rng.uniform(.40,.67); wf=rng.uniform(.095,.165)
        else: lf=rng.uniform(.20,.49); wf=rng.uniform(.045,.120)
        length=radius*length_ctl*lf*(.68+.32*energy); tangent_bias=rng.uniform(-.28,.28)*float(p["lightning.spread"]); pts=_bolt_path(p,radius,u,length,tangent_bias,jitter,rng); rootw=nominal*wf*rng.uniform(.82,1.22); taper_power=rng.uniform(1.08,1.55); pulse_freq=rng.uniform(1.3,2.3)
        ws=[]
        for i in range(len(pts)):
            q=i/(len(pts)-1); pulse=.82+.26*math.sin(math.tau*pulse_freq*q+bi*.73); ws.append(max(.0011,rootw*((1-q)**taper_power)*pulse))
        bridge=pts[:min(5,len(pts))]; bws=[max(.0012,rootw*(1.75-1.20*i/max(1,len(bridge)-1))) for i in range(len(bridge))]
        base.add_curve(f"{prefix}_major_root_glow_{bi}",bridge,[w*2.1 for w in bws],materials["core_glow"],layers["PLASMA"],z=.69,frame=index+1,frames=frames); base.add_curve(f"{prefix}_major_root_cyan_{bi}",bridge,bws,materials["inner"],layers["CORE"],z=.72,frame=index+1,frames=frames); base.add_curve(f"{prefix}_major_glow_{bi}",pts,[w*2.0 for w in ws],materials["lightning_glow"],layers["PLASMA"],z=.73,frame=index+1,frames=frames); base.add_curve(f"{prefix}_major_{bi}",pts,ws,materials["lightning"],layers["LIGHTNING"],z=.78,frame=index+1,frames=frames)
        branch_count=1+(1 if bi<2 and depth>1 and rng.random()<branch_p+.20 else 0)
        for level in range(branch_count):
            if rng.random()>branch_p+(.22 if bi<2 else .02): continue
            si=rng.randint(max(3,len(pts)//3),max(4,len(pts)-4)); bx,by=pts[si]; px0,py0=pts[si-1]; dx,dy=bx-px0,by-py0; dl=max(1e-6,math.hypot(dx,dy)); dx/=dl; dy/=dl; px,py=-dy,dx; bl=length*minor_len*rng.uniform(.28,.68)*(1.0-.16*level); sign=-1 if rng.random()<.5 else 1; bend_scale=rng.uniform(.16,.32)
            bpts=[]
            for j in range(9):
                q=j/8.; bend=sign*math.sin(math.pi*q)*bl*bend_scale; bpts.append((bx+dx*bl*q+px*bend,by+dy*bl*q+py*bend))
            bw=rootw*minor_ratio*rng.uniform(.52,.94); bws2=[max(.0010,bw*((1-j/8.)**1.22)) for j in range(9)]; base.add_curve(f"{prefix}_branch_glow_{bi}_{level}",bpts,[w*1.7 for w in bws2],materials["lightning_glow"],layers["PLASMA"],z=.74,frame=index+1,frames=frames); base.add_curve(f"{prefix}_branch_{bi}_{level}",bpts,bws2,materials["lightning"],layers["LIGHTNING"],z=.79,frame=index+1,frames=frames)
    micro_base=max(int(p["lightning.surface_crack_count"]),int(p["lightning.micro_count"])); micro=max(20,round(micro_base*1.35)); micro=round(micro*(1 if breakup<.34 else max(.22,1-(breakup-.34)*1.5)))
    for mi in range(micro):
        rng=random.Random(seed*99103+index*4099+mi*317); local=rng.uniform(.08,.94); u=tail+(head-tail)*local; x,y,a=v16.point_on_spine(radius,u,p); nx,ny=math.cos(a),math.sin(a); tx,ty=-math.sin(a),math.cos(a); x+=nx*nominal*rng.uniform(.25,1.10); y+=ny*nominal*rng.uniform(.25,1.10); ln=radius*rng.uniform(.018,.092)*length_ctl; sign=-1 if rng.random()<.5 else 1; bend=rng.uniform(-.22,.22); pts=[(x,y),(x+tx*ln*.43+nx*sign*ln*(.06+bend*.08),y+ty*ln*.43+ny*sign*ln*(.06+bend*.08)),(x+tx*ln+nx*sign*ln*bend,y+ty*ln+ny*sign*ln*bend)]; w=nominal*rng.uniform(.0045,.0135); base.add_curve(f"{prefix}_micro_{mi}",pts,[w,w*rng.uniform(.45,.75),.001],materials["lightning"],layers["LIGHTNING"],z=.735,frame=index+1,frames=frames)


def tri_visibility(u,v,tier,p,seed,index,frames,tri):
    if index!=frames-3: return _ORIG_TRI_VIS(u,v,tier,p,seed,index,frames,tri)
    if tier=="core": return 1.0
    rng=random.Random(seed*32452843+177); cavity_count=3 if tier=="body" else 2; deepest=99.0
    for ci in range(3):
        cu=rng.uniform(.18,.84); cv=rng.uniform(.18,.82); ru=rng.uniform(.035,.062); rv=rng.uniform(.105,.185); phase=rng.uniform(0,math.tau)
        if ci>=cavity_count: continue
        d=((u-cu)/ru)**2+((v-cv)/rv)**2; organic=.13*math.sin(math.tau*(4.8*u+2.3*v)+phase)+.07*math.sin(math.tau*(9.1*u-3.7*v)+phase*.43); deepest=min(deepest,d+organic)
    cutoff=.90 if tier=="body" else .62
    return 0.0 if deepest<cutoff else 1.0


def embed_sources(spec):
    v26.embed_sources(spec)
    try:
        text=bpy.data.texts.new("SOURCE_native_generate_vfx_v27.py"); text.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError: pass

v6.motion_window=motion_window
v9.add_ignition=add_ignition
v18.add_core=add_core
v21.add_lightning=add_lightning
v9.tri_visibility=tri_visibility
v17._band_polygon=v19._band_polygon
v12.point_on_spine=v16.point_on_spine; v9.point_on_spine=v16.point_on_spine; v8.point_on_spine=v16.point_on_spine; v7.point_on_spine=v16.point_on_spine; base.point_on_arc=v16.point_on_spine
base.setup_scene=setup_scene; base.make_materials=v14.make_materials; base.build_frame=v23.build_frame; base.embed_sources=embed_sources

if __name__=="__main__": base.main()
