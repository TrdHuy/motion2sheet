"""Blender-native VFX renderer V9: literal slash spline + coherent late dissolve."""
from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path

import bpy

_V8_PATH = Path(__file__).with_name("native_generate_vfx_v8.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v8", _V8_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load Blender-native V8 renderer")
v8 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v8)
v7, v6, base = v8.v7, v8.v6, v8.base
_base_embed_sources = v8._base_embed_sources

_CTRL = (
    (0.96, 1.43),
    (0.24, 1.19),
    (-0.27, 0.70),
    (-0.40, 0.05),
    (-0.20, -0.55),
    (0.36, -0.93),
    (1.06, -1.03),
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
    x += 0.045 * math.sin(math.tau * 1.55 * t + 0.35) + 0.018 * math.sin(math.tau * 3.1 * t + 0.9)
    y += 0.028 * math.sin(math.tau * 1.20 * t + 1.1)
    rot = math.radians(float(p.get("rotation", 0.0)))
    cr, sr = math.cos(rot), math.sin(rot)
    x, y = x * cr - y * sr, x * sr + y * cr
    x *= radius; y *= radius
    x += float(p["shape.offset_x"]) * radius * 3.35
    y -= float(p["shape.offset_y"]) * radius * 3.35
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
    belly, shoulder, lower = _g(u, .54, .27), _g(u, .23, .16), _g(u, .76, .16)
    pinch = _g(u, .39, .09)
    if side == "outer":
        v = .72 + .55 * belly + .20 * shoulder + .16 * lower - .13 * pinch
        v += .13 * math.sin(math.tau * 1.72 * u + phase) + .055 * math.sin(math.tau * 3.0 * u + phase * .45)
        return max(.24, v)
    v = .47 + .18 * belly - .12 * shoulder + .06 * lower
    v += .055 * math.sin(math.tau * 1.45 * u + phase * .67)
    return max(.18, v)


def tri_visibility(u, v, tier, p, seed, index, frames, tri):
    progress = base.dissolve_progress(p, index, frames, core=(tier == "core"))
    amount = float(p["dissolve.core_amount"] if tier == "core" else p["dissolve.inner_amount"] if tier == "inner" else p["dissolve.body_amount"])
    progress *= amount
    if progress <= 0.0:
        return 1.0
    phase = (seed % 997) * .013
    field = .52 + .19 * math.sin(math.tau * (2.45*u + .55*v) + phase)
    field += .14 * math.sin(math.tau * (5.15*u - 1.30*v) + phase * .43)
    field += .08 * math.sin(math.tau * (1.25*u + 3.8*v) + 1.4 + phase * .77)
    hr = random.Random(seed * 32452843 + 913)
    hole = 0.0
    for _ in range(8):
        cu, cv = hr.uniform(.08, .94), hr.uniform(.08, .92)
        ru, rv = hr.uniform(.055, .14), hr.uniform(.09, .22)
        d = ((u-cu)/ru)**2 + ((v-cv)/rv)**2
        if d < 1.0:
            hole = max(hole, (1.0-d)**.62)
    field -= hole * (.27 + .48 * progress)
    threshold = .23 + progress * .61
    edge = max(.040, float(p["dissolve.edge_softness"]) * .36)
    vis = base.smoothstep((field - threshold + edge) / (2.0 * edge))
    rr = random.Random(seed * 65537 + index * 8191 + tri * 313)
    return base.clamp01(vis + rr.uniform(-.045, .045))


def setup_scene(spec):
    scene, layers = v8.setup_scene(spec)
    scene["vfx_renderer"] = "blender-native-v9"
    scene["vfx_shape_model"] = "catmull-run144-slash"
    scene["vfx_breakup_model"] = "quads-powered-triangles-dissolve"
    return scene, layers


def add_ribbon(name, tier, p, radius, tail, head, material, collection, seed, index, frames, z, outer_scale, inner_scale, irregularity=1.0):
    samples, lanes = 118, 10
    nominal = float(p["thickness"]) * float(p["shape.body_scale"])
    rng = random.Random(seed * 1009 + sum(map(ord, name)))
    phase_a, phase_b = rng.uniform(0, math.tau), rng.uniform(0, math.tau)
    vertices, centers, widths = [], [], []
    for i in range(samples):
        u = i / (samples - 1)
        canonical = tail + (head - tail) * u
        x, y, angle = point_on_spine(radius, canonical, p)
        nx, ny = math.cos(angle), math.sin(angle)
        tx, ty = -math.sin(angle), math.cos(angle)
        env = base.smoothstep(u/.07) * base.smoothstep((1-u)/.05)
        shift = nominal * (.11*math.sin(math.tau*1.45*u + phase_a) + .045*math.sin(math.tau*2.75*u + phase_b))
        x += nx*shift + tx*nominal*.026*math.sin(math.tau*1.2*u + phase_b)
        y += ny*shift + ty*nominal*.026*math.sin(math.tau*1.2*u + phase_b)
        ow = nominal * outer_scale * env * macro_width(u, "outer", phase_a)
        iw = nominal * inner_scale * env * macro_width(u, "inner", phase_b)
        ow *= max(.25, 1.0 + irregularity*(.055*math.sin(math.tau*3.7*u+phase_b) + .025*math.sin(math.tau*7.1*u+phase_a)))
        iw *= max(.25, 1.0 + irregularity*.035*math.sin(math.tau*3.1*u+phase_a))
        centers.append((x,y,tx,ty,nx,ny)); widths.append((ow,iw))
        for lane in range(lanes+1):
            v = lane/lanes
            offset = -iw + (iw+ow)*v
            vertices.append((x+nx*offset, y+ny*offset, z))

    progress = base.dissolve_progress(p, index, frames, core=(tier == "core"))
    faces, removed = [], []
    dissolve_seed = v6._dissolve_seed(name, seed)
    tri_id = 0
    for i in range(1, samples):
        u = (i-.5)/(samples-1)
        x,y,tx,ty,nx,ny = centers[i]
        ow,iw = widths[i]
        for lane in range(lanes):
            a=(i-1)*(lanes+1)+lane; b=i*(lanes+1)+lane
            if progress <= 0.0:
                faces.append((a,a+1,b+1,b))
                continue
            tris=((a,a+1,b+1),(a,b+1,b)) if (i+lane)%2==0 else ((a,a+1,b),(a+1,b+1,b))
            for local_tri, tri in enumerate(tris):
                vv=base.clamp01((lane + (.33 if local_tri==0 else .67))/lanes)
                vis=tri_visibility(u,vv,tier,p,dissolve_seed,index,frames,tri_id)
                if vis < .50:
                    lateral=-iw+(iw+ow)*vv
                    removed.append((x+nx*lateral,y+ny*lateral,tx,ty,nx,ny,max((iw+ow)/lanes*.68,radius*.0045),1-vis,tier))
                else:
                    faces.append(tri)
                tri_id += 1
    mesh=bpy.data.meshes.new(name+"Mesh")
    mesh.from_pydata(vertices,[],faces); mesh.update()
    obj=bpy.data.objects.new(name,mesh); collection.objects.link(obj)
    obj.data.materials.append(material); base.key_visibility(obj,index+1,frames)
    return removed


def add_flow_bundle(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup):
    if breakup > .82: return
    nominal=float(p["thickness"])*float(p["shape.body_scale"])
    factor=1.0 if breakup < .45 else max(.18,1.0-(breakup-.45)*1.55)
    specs=(
        ("outer",max(3,round(12*factor)),.45,1.95,.065,.15,materials["outer"],layers["WISPS"]),
        ("body",max(4,round(15*factor)),.02,1.12,.075,.16,materials["body"],layers["WISPS"]),
        ("inner",max(1,round(2*factor)),-.36,-.10,.030,.052,materials["inner"],layers["CORE"]),
    )
    plume_slots={("outer",2),("outer",8),("body",3),("body",10)}
    for tier,count,omin,omax,wmin,wmax,mat,coll in specs:
        for stroke in range(count):
            rng=random.Random(seed*100003+stroke*7919+sum(map(ord,tier))*257)
            start,end=rng.uniform(.02,.16),rng.uniform(.84,.995)
            if end-start < .16: continue
            off=rng.uniform(omin,omax); phase=rng.uniform(0,math.tau); freq=rng.uniform(.72,1.55); width=rng.uniform(wmin,wmax)
            pts,ws=[],[]
            for i in range(52):
                q=i/51.0; u=start+(end-start)*q
                x,y,a=point_on_spine(radius,tail+(head-tail)*u,p)
                nx,ny=math.cos(a),math.sin(a); tx,ty=-math.sin(a),math.cos(a)
                wave=.10*math.sin(math.tau*freq*q+phase)+.03*math.sin(math.tau*2.2*q+phase*.4)
                x += nx*nominal*(off+wave)+tx*nominal*.025*math.sin(math.tau*1.25*q+phase)
                y += ny*nominal*(off+wave)+ty*nominal*.025*math.sin(math.tau*1.25*q+phase)
                env=base.smoothstep(q/.09)*base.smoothstep((1-q)/.075)
                pts.append((x,y)); ws.append(max(.0014,nominal*width*env*(1+.20*math.sin(math.tau*1.7*q+phase))))
            if (tier,stroke) in plume_slots and breakup < .45 and energy > .62:
                extend_end=stroke%2==0; ai=-1 if extend_end else 0; au=end if extend_end else start
                _,_,a=point_on_spine(radius,tail+(head-tail)*au,p)
                tx,ty=-math.sin(a),math.cos(a)
                if not extend_end: tx,ty=-tx,-ty
                px,py=-ty,tx; anchor=pts[ai]
                length=radius*float(p["shape.tongue_length"])*rng.uniform(.78,1.18)*(.76+.28*energy)
                rootw=max(ws[ai],nominal*width*.38); ep,ew=[],[]; sign=-1 if stroke%3==0 else 1
                for step in range(1,10):
                    q=step/9.0; bend=sign*math.sin(math.pi*q)*length*.075
                    ep.append((anchor[0]+tx*length*q+px*bend,anchor[1]+ty*length*q+py*bend)); ew.append(max(.0012,rootw*((1-q)**1.5)))
                if extend_end: pts+=ep; ws+=ew
                else: pts=list(reversed(ep))+pts; ws=list(reversed(ew))+ws
            z=.33 if tier=="outer" else .40 if tier=="body" else .51
            if tier!="inner":
                glow=materials["outer_glow"] if tier=="outer" else materials["body_glow"]
                base.add_curve(f"{prefix}_{tier}_flow_glow_{stroke}",pts,[w*1.55 for w in ws],glow,layers["PLASMA"],z=z-.025,frame=index+1,frames=frames)
            base.add_curve(f"{prefix}_{tier}_flow_{stroke}",pts,ws,mat,coll,z=z,frame=index+1,frames=frames)


def add_ignition(prefix,p,radius,materials,layers,seed,index,frames):
    # F1 is a dedicated ignition event, not a short prefix of the slash path.
    # Keep it safely inside the camera and bias it horizontally like Run 144.
    x = radius * 0.48
    y = radius * 0.58
    tx,ty,nx,ny = 1.0,0.0,0.0,1.0
    specs=(
        (.56,.34,materials["outer_glow"],layers["PLASMA"],.04),
        (.50,.30,materials["outer"],layers["BODY"],.10),
        (.39,.23,materials["body"],layers["BODY"],.16),
        (.18,.11,materials["inner"],layers["BODY"],.28),
    )
    for li,(tr,nr,mat,coll,z) in enumerate(specs):
        rng=random.Random(seed+li*131)
        p1,p2=rng.uniform(0,math.tau),rng.uniform(0,math.tau)
        loop=[]
        for k in range(28):
            aa=math.tau*k/28.0
            wobble=1.0+.14*math.sin(3*aa+p1)+.08*math.sin(5*aa+p2)
            loop.append((x+tx*radius*tr*wobble*math.cos(aa)+nx*radius*nr*math.sin(aa),y+ty*radius*tr*wobble*math.cos(aa)+ny*radius*nr*math.sin(aa)))
        base.add_polygon(f"{prefix}_ignition_{li}",loop,mat,coll,z=z,frame=index+1,frames=frames)


def build_frame(spec,index,materials,layers):
    p=spec["params"]; radius=float(p["radius"]); frames=int(spec["frames"]); seed=int(spec["seed"])
    tail,head,energy,breakup=v6.motion_window(index,frames,float(p["timing.peak"]))
    prefix=f"F{index+1:02d}"
    if index==0:
        add_ignition(prefix,p,radius,materials,layers,seed,index,frames); return
    removed=[]
    removed += add_ribbon(prefix+"_outer_haze","body",p,radius,tail,head,materials["outer_glow"],layers["PLASMA"],seed,index,frames,.02,3.15,.62,1.05)
    removed += add_ribbon(prefix+"_outer","body",p,radius,tail,head,materials["outer"],layers["BODY"],seed,index,frames,.08,2.62,.46,1.0)
    removed += add_ribbon(prefix+"_body","body",p,radius,tail,head,materials["body"],layers["BODY"],seed+31,index,frames,.14,1.60,.28,.88)
    removed += add_ribbon(prefix+"_inner","inner",p,radius,tail,head,materials["inner"],layers["BODY"],seed+47,index,frames,.28,.18,.055,.48)
    add_flow_bundle(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
    v8.add_hot_core(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
    v7.add_lightning(prefix,p,radius,tail,head,energy,breakup,materials,layers,seed,index,frames)
    v8.add_fragments(prefix,removed,p,materials,layers,radius,seed,index,frames,breakup)


def embed_sources(spec):
    _base_embed_sources(spec)
    for filename in ("native_generate_vfx_v6.py","native_generate_vfx_v7.py","native_generate_vfx_v8.py","native_generate_vfx_v9.py"):
        try:
            text=bpy.data.texts.new("SOURCE_"+filename)
            text.write(Path(__file__).with_name(filename).read_text(encoding="utf-8"))
        except OSError:
            pass


v8.point_on_spine=point_on_spine
v7.point_on_spine=point_on_spine
v7._macro_width=macro_width
v7._tri_visibility=tri_visibility
base.point_on_arc=point_on_spine
base.motion_window=v6.motion_window
base.setup_scene=setup_scene
base.make_materials=v8.make_materials
base.add_ribbon=add_ribbon
base.add_fragments=v8.add_fragments
base.build_frame=build_frame
base.embed_sources=embed_sources

if __name__ == "__main__":
    base.main()
