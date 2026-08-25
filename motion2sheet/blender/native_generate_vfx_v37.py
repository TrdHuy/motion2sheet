"""Blender-native VFX renderer V37: ignition rooted at the true upper slash start."""
from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path

import bpy

_V36_PATH = Path(__file__).with_name("native_generate_vfx_v36.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v36", _V36_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load V36")
v36 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v36)

v35, v34, v33, v32, v31, v30, v29, v28, v27, v23 = v36.v35, v36.v34, v36.v33, v36.v32, v36.v31, v36.v30, v36.v29, v36.v28, v36.v27, v36.v23
v21, v19, v18, v17, v16, v14 = v36.v21, v36.v19, v36.v18, v36.v17, v36.v16, v36.v14
v12, v9, v8, v7, v6, base = v36.v12, v36.v9, v36.v8, v36.v7, v36.v6, v36.base

_START_U = .06


def setup_scene(spec):
    scene, layers = v36.setup_scene(spec)
    scene["vfx_renderer"] = "blender-native-v37"
    scene["vfx_ignition_root"] = "upper-spine-start-u006"
    scene["vfx_f1_f2_continuity"] = "f1-root-equals-upper-f2-endpoint"
    return scene, layers


def _loop(cx, cy, rx, ry, points, phase, wobble=.12):
    out = []
    for i in range(points):
        a = math.tau * i / points
        w = 1.0 + wobble * math.sin(3*a + phase) + wobble*.55 * math.sin(5*a + phase*.47)
        out.append((cx + math.cos(a)*rx*w, cy + math.sin(a)*ry*w))
    return out


def add_ignition(prefix, p, radius, materials, layers, seed, index, frames):
    """Place every F1 ignition layer on the upper endpoint visible in F2."""
    nominal = float(p["thickness"]) * float(p["shape.body_scale"])
    x, y, _ = v16.point_on_spine(radius, _START_U, p)
    rng = random.Random(seed * 1301081 + 97)
    phase = rng.uniform(0.0, math.tau)

    # Same layered hot ignition language as V27/V28, but rooted at the actual
    # upper start of the current spline rather than the old middle anchor.
    rings = (
        (nominal*1.42, nominal*.92, materials["outer_glow"], layers["PLASMA"], .20),
        (nominal*1.08, nominal*.70, materials["outer"], layers["BODY"], .27),
        (nominal*.82, nominal*.54, materials["body"], layers["BODY"], .34),
        (nominal*.56, nominal*.38, materials["inner"], layers["CORE"], .48),
        (nominal*.34, nominal*.25, materials["core"], layers["CORE"], .66),
    )
    for li, (rx, ry, mat, coll, z) in enumerate(rings):
        base.add_polygon(
            f"{prefix}_ignition_ring_{li}",
            _loop(x, y, rx, ry, 30, phase + li*.63, .16 if li < 3 else .11),
            mat, coll, z=z, frame=index+1, frames=frames,
        )

    # White/cyan star rays, all sharing exactly the same upper root.
    for ri in range(12):
        rr = random.Random(seed*911382323 + ri*10007)
        ang = rr.uniform(0.0, math.tau)
        length = radius * rr.uniform(.15, .62) * (1.0 if ri < 7 else .72)
        start = nominal * rr.uniform(.22, .48)
        bend = rr.uniform(-.20, .20)
        pts = []
        steps = 5 if ri < 7 else 3
        for si in range(steps):
            q = si / max(1, steps-1)
            aa = ang + bend*math.sin(math.pi*q) + rr.uniform(-.045,.045)*(math.sin(math.pi*q)**.8)
            d = start + length*q
            pts.append((x + math.cos(aa)*d, y + math.sin(aa)*d))
        rootw = nominal * rr.uniform(.018, .065)
        ws = [max(.001, rootw*((1-si/max(1,steps-1))**1.25)) for si in range(steps)]
        base.add_curve(f"{prefix}_ignition_ray_glow_{ri}", pts, [w*2.0 for w in ws], materials["lightning_glow"], layers["PLASMA"], z=.70, frame=index+1, frames=frames)
        base.add_curve(f"{prefix}_ignition_ray_{ri}", pts, ws, materials["lightning"], layers["LIGHTNING"], z=.76, frame=index+1, frames=frames)

    # Five larger ignition bolts plus V28-style blue/cyan support rays.
    for bi in range(5):
        rr = random.Random(seed*700001 + bi*7919)
        ang = rr.uniform(0.0, math.tau)
        length = radius * rr.uniform(.25, .55)
        pts = [(x, y)]
        for si in range(1, 8):
            q = si / 7.0
            perp = rr.uniform(-1,1)*length*.055*math.sin(math.pi*q)
            dx, dy = math.cos(ang), math.sin(ang)
            px, py = -dy, dx
            pts.append((x + dx*length*q + px*perp, y + dy*length*q + py*perp))
        rootw = nominal * rr.uniform(.030, .095)
        ws = [max(.0012, rootw*((1-i/7.)**1.35)) for i in range(8)]
        base.add_curve(f"{prefix}_ignition_bolt_glow_{bi}", pts, [w*2.2 for w in ws], materials["lightning_glow"], layers["PLASMA"], z=.72, frame=index+1, frames=frames)
        base.add_curve(f"{prefix}_ignition_bolt_{bi}", pts, ws, materials["lightning"], layers["LIGHTNING"], z=.79, frame=index+1, frames=frames)

    for ri in range(10):
        rr = random.Random(seed*3133709 + ri*1013)
        ang = rr.uniform(0.0, math.tau)
        length = radius * rr.uniform(.24, .72)
        dx, dy = math.cos(ang), math.sin(ang)
        px, py = -dy, dx
        pts = []
        for si in range(6):
            q = si / 5.0
            bend = rr.uniform(-1,1)*length*.045*math.sin(math.pi*q)
            pts.append((x + dx*length*q + px*bend, y + dy*length*q + py*bend))
        rootw = nominal * rr.uniform(.025, .070)
        ws = [max(.0012, rootw*((1-i/5.)**1.12)) for i in range(6)]
        mat = materials["inner"] if ri % 3 == 0 else materials["body"]
        glow = materials["inner_glow"] if ri % 3 == 0 else materials["body_glow"]
        base.add_curve(f"{prefix}_support_glow_{ri}", pts, [w*3.0 for w in ws], glow, layers["PLASMA"], z=.58, frame=index+1, frames=frames)
        base.add_curve(f"{prefix}_support_{ri}", pts, [w*1.35 for w in ws], mat, layers["WISPS"], z=.63, frame=index+1, frames=frames)

    # Directional seed follows the actual spline inward from the upper start.
    seed_pts, seed_ws = [], []
    n = 30
    for i in range(n):
        q = i / (n-1)
        u = _START_U + .145*q
        sx, sy, a = v16.point_on_spine(radius, u, p)
        nx, ny = math.cos(a), math.sin(a)
        tx, ty = -math.sin(a), math.cos(a)
        wiggle = nominal*(.035*math.sin(math.tau*1.25*q+.6) + .012*math.sin(math.tau*3.1*q+1.7))
        sx += nx*wiggle + tx*nominal*.012*math.sin(math.pi*q)
        sy += ny*wiggle + ty*nominal*.012*math.sin(math.pi*q)
        env = (1.0-q)**.42
        pulse = .90 + .12*math.sin(math.tau*1.4*q+.4)
        seed_pts.append((sx, sy))
        seed_ws.append(max(.002, nominal*.32*env*pulse))

    base.add_curve(f"{prefix}_seed_outer_glow", seed_pts, [w*4.2 for w in seed_ws], materials["outer_glow"], layers["PLASMA"], z=.36, frame=index+1, frames=frames)
    base.add_curve(f"{prefix}_seed_body", seed_pts, [w*2.35 for w in seed_ws], materials["body"], layers["BODY"], z=.43, frame=index+1, frames=frames)
    base.add_curve(f"{prefix}_seed_inner_glow", seed_pts, [w*1.62 for w in seed_ws], materials["inner_glow"], layers["PLASMA"], z=.54, frame=index+1, frames=frames)
    base.add_curve(f"{prefix}_seed_inner", seed_pts, [w*1.05 for w in seed_ws], materials["inner"], layers["CORE"], z=.61, frame=index+1, frames=frames)
    base.add_curve(f"{prefix}_seed_hot", seed_pts, [w*.50 for w in seed_ws], materials["core"], layers["CORE"], z=.70, frame=index+1, frames=frames)

    side_rng = random.Random(seed * 510071 + 301)
    for wi, sign in enumerate((-1.0, 1.0)):
        wpts, wws = [], []
        wphase = side_rng.uniform(0.0, math.tau)
        for i in range(18):
            q = i / 17.0
            u = _START_U + .115*q
            sx, sy, a = v16.point_on_spine(radius, u, p)
            nx, ny = math.cos(a), math.sin(a)
            off = sign*nominal*(.32+.10*math.sin(math.pi*q+wphase))*math.sin(math.pi*q)
            sx += nx*off; sy += ny*off
            wpts.append((sx, sy))
            wws.append(max(.0013, nominal*.055*((1.0-q)**1.15)))
        base.add_curve(f"{prefix}_seed_wisp_glow_{wi}", wpts, [w*2.0 for w in wws], materials["body_glow"], layers["PLASMA"], z=.50, frame=index+1, frames=frames)
        base.add_curve(f"{prefix}_seed_wisp_{wi}", wpts, wws, materials["body"], layers["WISPS"], z=.57, frame=index+1, frames=frames)


def embed_sources(spec):
    v36.embed_sources(spec)
    try:
        text = bpy.data.texts.new("SOURCE_native_generate_vfx_v37.py")
        text.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError:
        pass

v29.tri_visibility = v32.tri_visibility
v9.tri_visibility = v32.tri_visibility
v9.add_ribbon = v29.add_ribbon
v8.add_fragments = v29.add_fragments
v9.add_ignition = add_ignition
v21.add_lightning = v35.add_lightning
v6.motion_window = v27.motion_window
v18.add_core = v33.add_core
v17._band_polygon = v36.band_polygon
v12.point_on_spine = v16.point_on_spine; v9.point_on_spine = v16.point_on_spine; v8.point_on_spine = v16.point_on_spine; v7.point_on_spine = v16.point_on_spine; base.point_on_arc = v16.point_on_spine
base.setup_scene = setup_scene; base.make_materials = v14.make_materials; base.build_frame = v23.build_frame; base.embed_sources = embed_sources

if __name__ == "__main__":
    base.main()
