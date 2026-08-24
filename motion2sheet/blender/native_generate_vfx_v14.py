"""Blender-native VFX renderer V14: contract-first organic plasma mass."""
from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path

import bpy

_V13_PATH = Path(__file__).with_name("native_generate_vfx_v13.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v13", _V13_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load Blender-native V13 renderer")
v13 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v13)
v12 = v13.v12
v9, v8, v7, v6, base = v12.v9, v12.v8, v12.v7, v12.v6, v12.base


def _g(u, c, w):
    return math.exp(-((u-c)/w)**2)


def macro_width(u, side, phase, p=None):
    """Asymmetric contract mass with real edge/detail noise in the contour."""
    belly = _g(u, .55, .24)
    upper = _g(u, .22, .14)
    lower = _g(u, .80, .15)
    waist = _g(u, .39, .075)
    flare = float(p["shape.flare"]) if p else .52
    taper = float(p["shape.taper_power"]) if p else .46
    edge_amp = float(p["shape.edge_noise"]) if p else 1.90
    edge_freq = float(p["shape.edge_noise_frequency"]) if p else 13.0
    detail_amp = float(p["shape.detail_noise"]) if p else .96
    detail_freq = float(p["shape.detail_noise_frequency"]) if p else 24.0
    # End taper is deliberately gentle: the contract asks for long energy tongues,
    # so the body narrows but does not collapse before those tongues take over.
    end_env = max(.30, (math.sin(math.pi*base.clamp01(u)) ** max(.18, taper)) * .78 + .22)
    coarse = math.sin(math.tau*(edge_freq*.075)*u + phase)
    detail = math.sin(math.tau*(detail_freq*.055)*u + phase*.43)
    if side == "outer":
        value = .62 + (1.04 + flare*.42)*belly + .28*upper + .34*lower - .22*waist
        value += .16*math.sin(math.tau*1.27*u + phase)
        value += edge_amp*.052*coarse + detail_amp*.030*detail
        return max(.18, value*end_env)
    value = .37 + .24*belly - .13*upper + .055*lower - .08*waist
    value += .050*math.sin(math.tau*1.53*u + phase*.61)
    value += edge_amp*.020*coarse + detail_amp*.013*detail
    return max(.12, value*end_env)


def setup_scene(spec):
    scene, layers = v13.setup_scene(spec)
    scene["vfx_renderer"] = "blender-native-v14"
    scene["vfx_authority"] = "contract-first"
    scene["vfx_body_model"] = "coherent-organic-mass"
    scene["vfx_tongue_model"] = "localized-edge-tongues"
    scene["vfx_hotspot_model"] = "localized-core-hotspots"
    return scene, layers


def make_materials(p):
    outer = base.hex_rgba(str(p["colors.outer"]))
    body = base.hex_rgba(str(p["colors.body"]))
    inner = base.hex_rgba(str(p["colors.inner"]))
    core = base.hex_rgba(str(p["colors.core"]))
    lightning = base.hex_rgba(str(p["colors.lightning"]))
    return {
        "outer": base.emission_material("VFX_Outer", outer, float(p["intensity.outer"])),
        "body": base.emission_material("VFX_Body", body, float(p["intensity.body"])),
        "inner": base.emission_material("VFX_Inner", inner, float(p["intensity.inner"])),
        "core": base.emission_material("VFX_Core", core, float(p["intensity.core"])),
        "lightning": base.emission_material("VFX_Lightning", lightning, float(p["intensity.lightning"])),
        "outer_glow": base.emission_material("VFX_OuterGlow", outer, .70 + float(p["glow.outer_strength"]), .16 + float(p["glow.outer_strength"])*.14),
        "body_glow": base.emission_material("VFX_BodyGlow", body, .72 + float(p["energy.glow_strength"])*.13, .12),
        "inner_glow": base.emission_material("VFX_InnerGlow", inner, .82 + float(p["glow.inner_strength"]), .09),
        "core_glow": base.emission_material("VFX_CoreGlow", core, 1.10 + float(p["glow.core_strength"])*1.5, .055),
        "lightning_glow": base.emission_material("VFX_LightningGlow", lightning, 1.05 + float(p["lightning.glow_strength"])*.20, .08),
    }


def _patched_macro(u, side, phase):
    return macro_width(u, side, phase, _ACTIVE_PARAMS)


_ACTIVE_PARAMS = None


def add_edge_tongues(prefix, p, radius, tail, head, energy, materials, layers, seed, index, frames, breakup):
    """Honor tongue_count without drawing dozens of full-length parallel ribbons."""
    if breakup > .78:
        return
    total = max(8, int(p["shape.tongue_count"]))
    nominal = float(p["thickness"])*float(p["shape.body_scale"])
    length_ctl = float(p["shape.tongue_length"])
    curve_ctl = float(p["shape.tongue_curve"])
    width_ctl = float(p["shape.tongue_width"])
    late = 1.0 if breakup < .36 else max(.16, 1.0-(breakup-.36)*1.7)
    count = max(5, round(total*late))
    for stroke in range(count):
        rng = random.Random(seed*131071 + stroke*4099 + index*8191)
        local = rng.uniform(.05,.96)
        u = tail + (head-tail)*local
        x,y,a = v12.point_on_spine(radius,u,p)
        nx,ny = math.cos(a),math.sin(a)
        tx,ty = -math.sin(a),math.cos(a)
        side = 1.0 if rng.random() < .72 else -1.0
        # Anchor most tongues close to the outer contour instead of stacking them
        # through the body as parallel full-length strokes.
        offset = nominal*(rng.uniform(.74,1.85) if side>0 else rng.uniform(-.34,-.10))
        x += nx*offset; y += ny*offset
        tangent_sign = 1.0 if rng.random() < .70 else -1.0
        length = radius*length_ctl*rng.uniform(.16,.54)*(0.58+.42*energy)
        if stroke in (2,9,17,27,34):
            length *= rng.uniform(1.55,2.15)
        bend_sign = -1.0 if stroke%3==0 else 1.0
        pts=[]; ws=[]
        phase=rng.uniform(0,math.tau)
        rootw=nominal*rng.uniform(.030,.075)*(.70+.65*width_ctl)
        for i in range(18):
            q=i/17.0
            bend = bend_sign*math.sin(math.pi*q)*length*.12*curve_ctl
            flutter = math.sin(math.tau*1.7*q+phase)*length*.018*curve_ctl
            pts.append((x+tx*tangent_sign*length*q+nx*(bend+flutter), y+ty*tangent_sign*length*q+ny*(bend+flutter)))
            env=(math.sin(math.pi*q)**.42)
            ws.append(max(.0010,rootw*env*((1-q)*.72+.28)))
        mat = materials["outer"] if side>0 and stroke%3 else materials["body"]
        if stroke%4==0:
            glow = materials["outer_glow"] if mat==materials["outer"] else materials["body_glow"]
            base.add_curve(f"{prefix}_tongue_glow_{stroke}",pts,[w*1.45 for w in ws],glow,layers["PLASMA"],z=.34,frame=index+1,frames=frames)
        base.add_curve(f"{prefix}_tongue_{stroke}",pts,ws,mat,layers["WISPS"],z=.43,frame=index+1,frames=frames)


def add_hotspots(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup):
    if energy < .58 or breakup > .62:
        return
    count=max(1,int(p["core.hotspot_count"]))
    scale=float(p["core.hotspot_scale"])
    nominal=float(p["thickness"])*float(p["shape.body_scale"])
    for hi in range(count):
        rng=random.Random(seed*500009 + hi*8101 + index*353)
        local=(hi+1)/(count+1) + rng.uniform(-.055,.055)
        u=tail+(head-tail)*base.clamp01(local)
        x,y,a=v12.point_on_spine(radius,u,p)
        nx,ny=math.cos(a),math.sin(a); tx,ty=-math.sin(a),math.cos(a)
        x += nx*nominal*rng.uniform(-.24,-.05)
        y += ny*nominal*rng.uniform(-.24,-.05)
        tr=nominal*rng.uniform(.18,.31)*scale
        nr=nominal*rng.uniform(.10,.20)*scale
        loop=[]
        phase=rng.uniform(0,math.tau)
        for k in range(20):
            aa=math.tau*k/20.0
            wobble=1.0+.15*math.sin(3*aa+phase)+.08*math.sin(5*aa+phase*.37)
            loop.append((x+tx*tr*wobble*math.cos(aa)+nx*nr*math.sin(aa), y+ty*tr*wobble*math.cos(aa)+ny*nr*math.sin(aa)))
        base.add_polygon(f"{prefix}_hotspot_glow_{hi}",loop,materials["core_glow"],layers["PLASMA"],z=.60,frame=index+1,frames=frames)
        inner=[(x+(px-x)*.62,y+(py-y)*.62) for px,py in loop]
        base.add_polygon(f"{prefix}_hotspot_{hi}",inner,materials["core"],layers["CORE"],z=.66,frame=index+1,frames=frames)


def build_frame(spec,index,materials,layers):
    global _ACTIVE_PARAMS
    p=spec["params"]; _ACTIVE_PARAMS=p
    radius=float(p["radius"]); frames=int(spec["frames"]); seed=int(spec["seed"])
    tail,head,energy,breakup=v6.motion_window(index,frames,float(p["timing.peak"]))
    prefix=f"F{index+1:02d}"
    if index==0:
        v9.add_ignition(prefix,p,radius,materials,layers,seed,index,frames)
        return

    removed=[]
    # Four coherent masses only.  Fine texture now comes from edge tongues,
    # hotspots and lightning, not dozens of parallel body ribbons.
    removed += v9.add_ribbon(prefix+"_outer_glow","body",p,radius,tail,head,materials["outer_glow"],layers["PLASMA"],seed,index,frames,.02,3.05,.48,1.18)
    removed += v9.add_ribbon(prefix+"_outer","body",p,radius,tail,head,materials["outer"],layers["BODY"],seed+7,index,frames,.08,2.58,.34,1.15)
    removed += v9.add_ribbon(prefix+"_body","body",p,radius,tail,head,materials["body"],layers["BODY"],seed+31,index,frames,.14,1.54,.20,1.02)
    removed += v9.add_ribbon(prefix+"_inner","inner",p,radius,tail,head,materials["inner"],layers["BODY"],seed+47,index,frames,.28,.18,.040,.62)

    add_edge_tongues(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
    v12.add_hot_core(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
    add_hotspots(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
    v12.add_lightning(prefix,p,radius,tail,head,energy,breakup,materials,layers,seed,index,frames)
    v8.add_fragments(prefix,removed,p,materials,layers,radius,seed,index,frames,breakup)
    if index==frames-1:
        v13.add_terminal_shards(prefix,p,radius,tail,head,materials,layers,seed,index,frames)


def embed_sources(spec):
    v13.embed_sources(spec)
    try:
        text=bpy.data.texts.new("SOURCE_native_generate_vfx_v14.py")
        text.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError:
        pass


# Reused V9 ribbon code resolves these globals dynamically.
v9.macro_width=_patched_macro
v9.point_on_spine=v12.point_on_spine
v8.point_on_spine=v12.point_on_spine
v7.point_on_spine=v12.point_on_spine
base.setup_scene=setup_scene
base.make_materials=make_materials
base.build_frame=build_frame
base.embed_sources=embed_sources

if __name__ == "__main__":
    base.main()
