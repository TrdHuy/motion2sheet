"""Blender-native VFX renderer V12: contract-first organic lightning slash."""
from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path

import bpy

_V11_PATH = Path(__file__).with_name("native_generate_vfx_v11.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v11", _V11_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load Blender-native V11 renderer")
v11 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v11)
v10, v9, v8, v7, v6, base = v11.v10, v11.v9, v11.v8, v11.v7, v11.v6, v11.base

_CTRL = (
    (1.02, 1.16),
    (0.43, 1.08),
    (-0.08, 0.82),
    (-0.38, 0.43),
    (-0.32, 0.02),
    (-0.06, -0.37),
    (0.28, -0.70),
    (1.02, -0.90),
)


def _catmull(p0, p1, p2, p3, t):
    t2, t3 = t * t, t * t * t
    return (
        0.5 * ((2*p1[0]) + (-p0[0] + p2[0])*t + (2*p0[0] - 5*p1[0] + 4*p2[0] - p3[0])*t2 + (-p0[0] + 3*p1[0] - 3*p2[0] + p3[0])*t3),
        0.5 * ((2*p1[1]) + (-p0[1] + p2[1])*t + (2*p0[1] - 5*p1[1] + 4*p2[1] - p3[1])*t2 + (-p0[1] + 3*p1[1] - 3*p2[1] + p3[1])*t3),
    )


def _raw_spine(radius, t, p):
    t = base.clamp01(t)
    nseg = len(_CTRL) - 1
    s = t * nseg
    seg = min(nseg - 1, int(s))
    q = s - seg
    p1, p2 = _CTRL[seg], _CTRL[seg + 1]
    p0 = _CTRL[seg - 1] if seg > 0 else p1
    p3 = _CTRL[seg + 2] if seg + 2 < len(_CTRL) else p2
    x, y = _catmull(p0, p1, p2, p3, q)
    form = float(p["shape.form_noise"])
    ff = float(p["shape.form_noise_frequency"])
    x += form * (0.044 * math.sin(math.tau * (0.52 * ff) * t + 0.31)
                 + 0.016 * math.sin(math.tau * (0.91 * ff) * t + 1.17))
    y += form * (0.034 * math.sin(math.tau * (0.43 * ff) * t + 0.94)
                 + 0.012 * math.sin(math.tau * (0.78 * ff) * t + 0.22))
    rot = math.radians(float(p.get("rotation", 0.0)))
    cr, sr = math.cos(rot), math.sin(rot)
    x, y = x * cr - y * sr, x * sr + y * cr
    x *= radius
    y *= radius
    x += float(p["shape.offset_x"]) * radius * 2.92
    y -= float(p["shape.offset_y"]) * radius * 2.92
    return x, y


def point_on_spine(radius, t, p):
    x, y = _raw_spine(radius, t, p)
    e = 0.0015
    xa, ya = _raw_spine(radius, max(0.0, t - e), p)
    xb, yb = _raw_spine(radius, min(1.0, t + e), p)
    return x, y, math.atan2(yb - ya, xb - xa) - math.pi * 0.5


def _g(u, c, w):
    return math.exp(-((u - c) / w) ** 2)


def macro_width(u, side, phase):
    belly = _g(u, .54, .25)
    upper = _g(u, .23, .14)
    lower = _g(u, .79, .15)
    waist = _g(u, .39, .075)
    if side == "outer":
        value = .66 + .90 * belly + .31 * upper + .38 * lower - .20 * waist
        value += .17 * math.sin(math.tau * 1.35 * u + phase)
        value += .085 * math.sin(math.tau * 3.25 * u + phase * .47)
        return max(.20, value)
    value = .42 + .24 * belly - .15 * upper + .06 * lower - .08 * waist
    value += .055 * math.sin(math.tau * 1.55 * u + phase * .61)
    return max(.15, value)


def tri_visibility(u, v, tier, p, seed, index, frames, tri):
    progress = base.dissolve_progress(p, index, frames, core=(tier == "core"))
    amount = float(p["dissolve.core_amount"] if tier == "core" else p["dissolve.inner_amount"] if tier == "inner" else p["dissolve.body_amount"])
    progress *= amount
    if progress <= 0.0:
        return 1.0
    scale = max(.025, float(p["dissolve.noise_scale"]))
    detail = float(p["dissolve.noise_detail"])
    phase = (seed % 997) * .013
    f1 = max(1.20, min(3.40, .18 / scale))
    f2 = f1 * (1.65 + .10 * detail)
    field = .53 + .20 * math.sin(math.tau * (f1*u + .48*v) + phase)
    field += .13 * math.sin(math.tau * (f2*u - 1.20*v) + phase * .43)
    field += .075 * math.sin(math.tau * (1.12*u + 3.35*v) + 1.28 + phase * .71)
    hr = random.Random(seed * 32452843 + 913)
    hole = 0.0
    for _ in range(10):
        cu, cv = hr.uniform(.06, .96), hr.uniform(.05, .95)
        ru, rv = hr.uniform(.050, .145), hr.uniform(.080, .235)
        d = ((u-cu)/ru)**2 + ((v-cv)/rv)**2
        if d < 1.0:
            hole = max(hole, (1.0-d)**.60)
    field -= hole * (.30 + .62 * progress)
    threshold = .245 + progress * .80
    edge = max(.038, float(p["dissolve.edge_softness"]) * .34)
    vis = base.smoothstep((field - threshold + edge) / (2.0 * edge))
    rr = random.Random(seed * 65537 + index * 8191 + tri * 313)
    return base.clamp01(vis + rr.uniform(-.040, .040))


def setup_scene(spec):
    scene, layers = v11.setup_scene(spec)
    scene["vfx_renderer"] = "blender-native-v12"
    scene["vfx_authority"] = "lightning_slash_contract.json5"
    scene["vfx_shape_model"] = "open-asymmetric-contract-spline"
    scene["vfx_flow_model"] = "profile-tongue-count-and-length"
    scene["vfx_core_model"] = "profile-five-streak-hot-core"
    scene["vfx_lightning_model"] = "profile-major-branch-micro-hierarchy"
    return scene, layers


def add_flow_bundle(prefix, p, radius, tail, head, energy, materials, layers, seed, index, frames, breakup):
    if breakup > .87:
        return
    total = max(6, int(p["shape.tongue_count"]))
    outer_n = max(3, round(total * .37))
    body_n = max(3, round(total * .47))
    inner_n = max(1, total - outer_n - body_n)
    nominal = float(p["thickness"]) * float(p["shape.body_scale"])
    length_ctl = float(p["shape.tongue_length"])
    curve_ctl = float(p["shape.tongue_curve"])
    width_ctl = float(p["shape.tongue_width"])
    factor = 1.0 if breakup < .42 else max(.12, 1.0 - (breakup-.42)*1.65)
    specs = (
        ("outer", max(2, round(outer_n*factor)), .55, 2.65, .055, .145, materials["outer"], layers["WISPS"]),
        ("body", max(3, round(body_n*factor)), -.04, 1.45, .060, .155, materials["body"], layers["WISPS"]),
        ("inner", max(1, round(inner_n*factor)), -.39, -.06, .030, .060, materials["inner"], layers["CORE"]),
    )
    plume_slots = {("outer",1), ("outer",6), ("outer",11), ("body",2), ("body",9), ("body",15)}
    for tier, count, omin, omax, wmin, wmax, mat, coll in specs:
        for stroke in range(count):
            rng = random.Random(seed*100003 + stroke*7919 + sum(map(ord,tier))*257)
            start = rng.uniform(.00, .17)
            end = rng.uniform(.80, 1.00)
            if breakup > .42:
                trim = base.clamp01((breakup-.42)/.45)
                start += trim*rng.uniform(.02,.18)
                end -= trim*rng.uniform(.05,.23)
            if end-start < .15:
                continue
            off = rng.uniform(omin, omax)
            phase = rng.uniform(0, math.tau)
            freq = rng.uniform(.60, 1.65)
            width = rng.uniform(wmin, wmax) * (.75 + .55*width_ctl)
            pts, ws = [], []
            for i in range(60):
                q = i/59.0
                u = start + (end-start)*q
                x,y,a = point_on_spine(radius, tail+(head-tail)*u, p)
                nx,ny = math.cos(a),math.sin(a)
                tx,ty = -math.sin(a),math.cos(a)
                wave = curve_ctl*(.11*math.sin(math.tau*freq*q+phase) + .038*math.sin(math.tau*2.4*q+phase*.37))
                x += nx*nominal*(off+wave) + tx*nominal*.045*math.sin(math.tau*1.20*q+phase)
                y += ny*nominal*(off+wave) + ty*nominal*.045*math.sin(math.tau*1.20*q+phase)
                env = base.smoothstep(q/.075)*base.smoothstep((1-q)/.060)
                w = nominal*width*env*(1+.25*math.sin(math.tau*1.75*q+phase))
                pts.append((x,y)); ws.append(max(.0012,w))
            if (tier,stroke) in plume_slots and breakup < .42 and energy > .62:
                extend_end = (stroke % 2) == 1
                ai, au = (-1,end) if extend_end else (0,start)
                _,_,a = point_on_spine(radius, tail+(head-tail)*au, p)
                tx,ty = -math.sin(a),math.cos(a)
                if not extend_end:
                    tx,ty = -tx,-ty
                px,py = -ty,tx
                anchor = pts[ai]
                length = radius*length_ctl*rng.uniform(.68,1.15)*(.72+.26*energy)
                rootw = max(ws[ai], nominal*width*.36)
                extp, extw = [], []
                sign = -1.0 if stroke%3==0 else 1.0
                for step in range(1,11):
                    q = step/10.0
                    bend = sign*math.sin(math.pi*q)*length*.090*curve_ctl
                    jitter = math.sin(math.tau*2.0*q+phase)*length*.012*curve_ctl
                    extp.append((anchor[0]+tx*length*q+px*(bend+jitter), anchor[1]+ty*length*q+py*(bend+jitter)))
                    extw.append(max(.0010,rootw*((1-q)**1.42)))
                if extend_end:
                    pts += extp; ws += extw
                else:
                    pts = list(reversed(extp))+pts; ws = list(reversed(extw))+ws
            z = .33 if tier=="outer" else .40 if tier=="body" else .52
            if tier != "inner" and stroke % 2 == 0:
                glow = materials["outer_glow"] if tier=="outer" else materials["body_glow"]
                base.add_curve(f"{prefix}_{tier}_flow_glow_{stroke}", pts, [w*1.48 for w in ws], glow, layers["PLASMA"], z=z-.025, frame=index+1, frames=frames)
            base.add_curve(f"{prefix}_{tier}_flow_{stroke}", pts, ws, mat, coll, z=z, frame=index+1, frames=frames)


def add_hot_core(prefix, p, radius, tail, head, energy, materials, layers, seed, index, frames, breakup):
    heat = base.smoothstep((energy-.55)/.45)
    if heat < .02 or breakup > .80:
        return
    nominal = float(p["thickness"])*float(p["shape.body_scale"])
    count = max(2, int(p["core.streak_count"]))
    center_jitter = float(p["core.center_jitter"])/max(1.0,float(p["core.width_max"]))
    width_jitter = float(p["core.width_jitter"])
    split_p = float(p["core.split_probability"])
    base_scale = float(p["shape.core_scale"])
    late = max(.05, 1.0-max(0.0,breakup-.20)*1.55)
    for stroke in range(count):
        rng = random.Random(seed*900001 + stroke*611 + index*3571)
        phase = rng.uniform(0,math.tau)
        freq = rng.uniform(1.25,2.65)
        lane = (-.46 + (.38*stroke/max(1,count-1)))
        pts, widths, gaps = [], [], set()
        if split_p > 0:
            ngap = 1 + (1 if rng.random() < split_p else 0)
            for _ in range(ngap):
                gaps.add(round(rng.uniform(.20,.82),2))
        for i in range(92):
            q=i/91.0
            x,y,a=point_on_spine(radius,tail+(head-tail)*q,p)
            nx,ny=math.cos(a),math.sin(a); tx,ty=-math.sin(a),math.cos(a)
            local = lane + center_jitter*(.62*math.sin(math.tau*freq*q+phase)+.23*math.sin(math.tau*3.2*q+phase*.44))
            x += nx*nominal*local + tx*nominal*.055*math.sin(math.tau*2.65*q+phase)
            y += ny*nominal*local + ty*nominal*.055*math.sin(math.tau*2.65*q+phase)
            pinch=1.0
            for c in (.25+.025*stroke,.52+.018*stroke,.75-.018*stroke):
                d=abs(q-c)
                if d<.045: pinch*=.14+.86*d/.045
            jitter=1.0+width_jitter*.40*math.sin(math.tau*2.1*q+phase)
            w=nominal*base_scale*(.22+.08*(stroke%3))*pinch*max(.16,jitter)*heat*late
            pts.append((x,y)); widths.append(max(.0011,w))
        chunks=[]; cp=[]; cw=[]
        for i,(pt,w) in enumerate(zip(pts,widths)):
            q=i/91.0
            gap=any(abs(q-g)<(.018+.010*split_p) for g in gaps)
            if gap:
                if len(cp)>=2: chunks.append((cp,cw))
                cp=[]; cw=[]
            else:
                cp.append(pt); cw.append(w)
        if len(cp)>=2: chunks.append((cp,cw))
        for ci,(cpts,cws) in enumerate(chunks):
            base.add_curve(f"{prefix}_core_cyan_{stroke}_{ci}",cpts,[w*2.25 for w in cws],materials["inner_glow"],layers["PLASMA"],z=.57,frame=index+1,frames=frames)
            base.add_curve(f"{prefix}_core_white_{stroke}_{ci}",cpts,cws,materials["core"],layers["CORE"],z=.64,frame=index+1,frames=frames)


def _bolt_points(radius, p, u, outward, length, jitter, rng):
    x,y,a=point_on_spine(radius,u,p)
    nx,ny=math.cos(a),math.sin(a); tx,ty=-math.sin(a),math.cos(a)
    if outward < 0: nx,ny=-nx,-ny
    pts=[]; phase=rng.uniform(0,math.tau)
    for i in range(12):
        q=i/11.0
        side=math.sin(math.pi*q)*(math.sin(math.tau*2.1*q+phase)*jitter*length*.17 + rng.uniform(-1,1)*jitter*length*.035)
        pts.append((x+nx*length*q+tx*side,y+ny*length*q+ty*side))
    return pts


def add_lightning(prefix,p,radius,tail,head,energy,breakup,materials,layers,seed,index,frames):
    if energy < .50 or breakup > .74:
        return
    rng=random.Random(seed*700001+index*10007)
    major=max(1,int(p["lightning.major_count"]))
    jitter=float(p["lightning.jitter"]); length_ctl=float(p["lightning.length"])
    branch_p=float(p["lightning.branch_probability"]); depth=max(0,int(p["lightning.branch_depth"]))
    minor_ratio=float(p["lightning.minor_width_ratio"]); minor_len=float(p["lightning.minor_length_ratio"])
    nominal=float(p["thickness"])*float(p["shape.body_scale"])
    anchors=(.31,.67,.48)
    for bi in range(major):
        u=tail+(head-tail)*anchors[bi%len(anchors)]
        outward=1 if bi%2==0 else -1
        length=radius*length_ctl*rng.uniform(.27,.40)*(.72+.28*energy)
        pts=_bolt_points(radius,p,u,outward,length,jitter,rng)
        rootw=nominal*rng.uniform(.036,.058)
        ws=[max(.0010,rootw*((1-i/(len(pts)-1))**1.35)) for i in range(len(pts))]
        base.add_curve(f"{prefix}_major_lightning_glow_{bi}",pts,[w*1.65 for w in ws],materials["lightning_glow"],layers["PLASMA"],z=.69,frame=index+1,frames=frames)
        base.add_curve(f"{prefix}_major_lightning_{bi}",pts,ws,materials["lightning"],layers["LIGHTNING"],z=.72,frame=index+1,frames=frames)
        if depth>0 and rng.random()<branch_p:
            start_i=rng.randint(4,8); bx,by=pts[start_i]
            dx=pts[start_i][0]-pts[start_i-1][0]; dy=pts[start_i][1]-pts[start_i-1][1]
            dl=max(1e-6,math.hypot(dx,dy)); dx/=dl; dy/=dl; px,py=-dy,dx
            bl=length*minor_len*rng.uniform(.45,.75); sign=-1 if bi%2==0 else 1
            bpts=[(bx+dx*bl*q+px*sign*math.sin(math.pi*q)*bl*.24,by+dy*bl*q+py*sign*math.sin(math.pi*q)*bl*.24) for q in (0,.18,.36,.55,.73,.88,1.0)]
            bws=[max(.0010,rootw*minor_ratio*((1-i/(len(bpts)-1))**1.25)) for i in range(len(bpts))]
            base.add_curve(f"{prefix}_branch_{bi}",bpts,bws,materials["lightning"],layers["LIGHTNING"],z=.73,frame=index+1,frames=frames)
    micro=max(int(p["lightning.surface_crack_count"]),int(p["lightning.micro_count"]))
    micro=round(micro*(1.0 if breakup<.35 else max(.22,1-(breakup-.35)*1.55)))
    mw=nominal*.0105
    for mi in range(micro):
        rr=random.Random(seed*99001+index*4099+mi*313)
        local=rr.uniform(.12,.90); u=tail+(head-tail)*local
        x,y,a=point_on_spine(radius,u,p)
        nx,ny=math.cos(a),math.sin(a); tx,ty=-math.sin(a),math.cos(a)
        lateral=nominal*rr.uniform(-.22,.80); x+=nx*lateral; y+=ny*lateral
        ln=radius*rr.uniform(.035,.078)*length_ctl; sign=-1 if rr.random()<.5 else 1
        pts=[(x,y),(x+tx*ln*.45+nx*sign*ln*.12,y+ty*ln*.45+ny*sign*ln*.12),(x+tx*ln,y+ty*ln)]
        base.add_curve(f"{prefix}_micro_{mi}",pts,[mw,mw*.72,.0010],materials["lightning"],layers["LIGHTNING"],z=.70,frame=index+1,frames=frames)


def build_frame(spec,index,materials,layers):
    p=spec["params"]
    radius=float(p["radius"]); frames=int(spec["frames"]); seed=int(spec["seed"])
    tail,head,energy,breakup=v6.motion_window(index,frames,float(p["timing.peak"]))
    prefix=f"F{index+1:02d}"
    if index==0:
        v9.add_ignition(prefix,p,radius,materials,layers,seed,index,frames); return
    removed=[]
    if index>=frames-2:
        removed += v9.add_ribbon(prefix+"_coherent_underlay","body",p,radius,tail,head,materials["outer"],layers["BODY"],seed+113,index,frames,.045,3.28,.62,.74)
    removed += v9.add_ribbon(prefix+"_outer_haze","body",p,radius,tail,head,materials["outer_glow"],layers["PLASMA"],seed,index,frames,.02,3.12,.50,1.12)
    removed += v9.add_ribbon(prefix+"_outer","body",p,radius,tail,head,materials["outer"],layers["BODY"],seed,index,frames,.08,2.58,.37,1.10)
    removed += v9.add_ribbon(prefix+"_body","body",p,radius,tail,head,materials["body"],layers["BODY"],seed+31,index,frames,.14,1.52,.22,.98)
    removed += v9.add_ribbon(prefix+"_inner","inner",p,radius,tail,head,materials["inner"],layers["BODY"],seed+47,index,frames,.28,.16,.040,.58)
    add_flow_bundle(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
    add_hot_core(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
    add_lightning(prefix,p,radius,tail,head,energy,breakup,materials,layers,seed,index,frames)
    v8.add_fragments(prefix,removed,p,materials,layers,radius,seed,index,frames,breakup)


def embed_sources(spec):
    v9.embed_sources(spec)
    try:
        text=bpy.data.texts.new("SOURCE_native_generate_vfx_v12.py")
        text.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError:
        pass


v9.point_on_spine=point_on_spine
v8.point_on_spine=point_on_spine
v7.point_on_spine=point_on_spine
v9.macro_width=macro_width
v9.tri_visibility=tri_visibility
base.point_on_arc=point_on_spine
base.setup_scene=setup_scene
base.build_frame=build_frame
base.embed_sources=embed_sources

if __name__ == "__main__":
    base.main()
