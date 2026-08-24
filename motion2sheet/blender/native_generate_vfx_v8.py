"""Blender-native VFX renderer V8: Run-144 silhouette parity pass."""
from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path

import bpy

_V7_PATH = Path(__file__).with_name("native_generate_vfx_v7.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v7", _V7_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load Blender-native V7 renderer")
v7 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v7)
v6 = v7.v6
base = v7.base
_base_embed_sources = v7._base_embed_sources


def _g(u, c, w):
    return math.exp(-((u - c) / w) ** 2)


def _raw_spine(radius, t, p):
    t = base.clamp01(t)
    tw = t + 0.080 * math.sin(math.pi * t) - 0.048 * math.sin(math.tau * t)
    tw += 0.024 * math.sin(math.tau * 2.0 * t + 0.42)
    angle = math.radians(float(p["start_angle"]) + float(p["arc_angle"]) * tw + float(p["rotation"]))
    radial = 1.0 + 0.155 * math.sin(math.tau * (t - 0.10)) + 0.075 * math.sin(math.tau * 2.0 * t + 0.58)
    radial -= 0.135 * _g(t, 0.50, 0.15)
    radial += 0.120 * _g(t, 0.80, 0.15) + 0.055 * _g(t, 0.18, 0.13)
    x, y = radius * radial * math.cos(angle), radius * radial * math.sin(angle)
    tx, ty = -math.sin(angle), math.cos(angle)
    nx, ny = math.cos(angle), math.sin(angle)
    tang = radius * (-0.115 * _g(t, 0.13, 0.15) + 0.085 * _g(t, 0.84, 0.15) + 0.038 * math.sin(math.tau * t + 0.08))
    norm = radius * (0.095 * math.sin(math.tau * 1.23 * t + 0.46) - 0.058 * math.sin(math.tau * 2.42 * t + 0.92))
    x += tx * tang + nx * norm
    y += ty * tang + ny * norm
    x += float(p["shape.offset_x"]) * radius * 3.35
    y -= float(p["shape.offset_y"]) * radius * 3.35
    return x, y


def point_on_spine(radius, t, p):
    x, y = _raw_spine(radius, t, p)
    e = 0.0015
    xa, ya = _raw_spine(radius, max(0.0, t - e), p)
    xb, yb = _raw_spine(radius, min(1.0, t + e), p)
    return x, y, math.atan2(yb - ya, xb - xa) - math.pi * 0.5


def macro_width(u, side, phase):
    belly, shoulder, lower, pinch = _g(u, .56, .27), _g(u, .23, .18), _g(u, .78, .16), _g(u, .43, .10)
    if side == "outer":
        v = .73 + .88 * belly + .36 * shoulder + .30 * lower - .18 * pinch
        v += .16 * math.sin(math.tau * 1.72 * u + phase) + .08 * math.sin(math.tau * 3.35 * u + phase * .43)
        return max(.24, v)
    return max(.20, .48 + .21 * belly - .14 * shoulder + .08 * lower + .075 * math.sin(math.tau * 1.55 * u + phase * .67))


def tri_visibility(u, v, tier, p, seed, index, frames, tri):
    progress = base.dissolve_progress(p, index, frames, core=(tier == "core"))
    amount = float(p["dissolve.core_amount"] if tier == "core" else p["dissolve.inner_amount"] if tier == "inner" else p["dissolve.body_amount"])
    progress *= amount
    if progress <= 0.0:
        return 1.0
    phase = (seed % 997) * .013
    field = .50 + .20 * math.sin(math.tau * (3.15 * u + .42 * v) + phase)
    field += .15 * math.sin(math.tau * (6.2 * u - 1.35 * v) + phase * .41)
    field += .10 * math.sin(math.tau * (1.55 * u + 4.7 * v) + 1.7 + phase * .73)
    hr = random.Random(seed * 32452843 + 913)
    hole = 0.0
    for _ in range(9):
        cu, cv = hr.uniform(.08, .94), hr.uniform(.08, .92)
        ru, rv = hr.uniform(.045, .13), hr.uniform(.08, .24)
        d = ((u - cu) / ru) ** 2 + ((v - cv) / rv) ** 2
        if d < 1.0:
            hole = max(hole, (1.0 - d) ** .65)
    field -= hole * (.30 + .52 * progress)
    threshold = .26 + progress * .64
    edge = max(.035, float(p["dissolve.edge_softness"]) * .34)
    vis = base.smoothstep((field - threshold + edge) / (2.0 * edge))
    rr = random.Random(seed * 65537 + index * 8191 + tri * 313)
    return base.clamp01(vis + rr.uniform(-.05, .05))


def setup_scene(spec):
    scene, layers = v7.setup_scene(spec)
    scene["vfx_renderer"] = "blender-native-v8"
    scene["vfx_shape_model"] = "run144-asymmetric-wide-mass"
    scene["vfx_breakup_model"] = "clustered-organic-triangles"
    return scene, layers


def make_materials(p):
    outer, body = base.hex_rgba(str(p["colors.outer"])), base.hex_rgba(str(p["colors.body"]))
    inner, core = base.hex_rgba(str(p["colors.inner"])), base.hex_rgba(str(p["colors.core"]))
    lightning = base.hex_rgba(str(p["colors.lightning"]))
    return {
        "outer": base.emission_material("VFX_Outer", outer, .88),
        "body": base.emission_material("VFX_Body", body, .93),
        "inner": base.emission_material("VFX_Inner", inner, .90),
        "core": base.emission_material("VFX_Core", core, 2.05),
        "lightning": base.emission_material("VFX_Lightning", lightning, 3.15),
        "outer_glow": base.emission_material("VFX_OuterGlow", outer, .62, .18),
        "body_glow": base.emission_material("VFX_BodyGlow", body, .70, .15),
        "inner_glow": base.emission_material("VFX_InnerGlow", inner, .76, .10),
        "lightning_glow": base.emission_material("VFX_LightningGlow", lightning, 1.02, .10),
    }


def add_flow_bundle(prefix, p, radius, tail, head, energy, materials, layers, seed, index, frames, breakup):
    if breakup > .88:
        return
    nominal = float(p["thickness"]) * float(p["shape.body_scale"])
    factor = 1.0 if breakup < .48 else max(.20, 1.0 - (breakup - .48) * 1.45)
    specs = (
        ("outer", max(3, round(18 * factor)), .70, 3.40, .075, .18, materials["outer"], layers["WISPS"]),
        ("body", max(4, round(22 * factor)), .02, 1.90, .085, .19, materials["body"], layers["WISPS"]),
        ("inner", max(1, round(3 * factor)), -.40, -.08, .034, .060, materials["inner"], layers["CORE"]),
    )
    plumes = {("outer", 2), ("outer", 10), ("outer", 15), ("body", 4), ("body", 13), ("body", 19)}
    for tier, count, omin, omax, wmin, wmax, mat, coll in specs:
        for stroke in range(count):
            rng = random.Random(seed * 100003 + stroke * 7919 + sum(map(ord, tier)) * 257)
            start, end = rng.uniform(.02, .18), rng.uniform(.82, .995)
            if breakup > .48:
                trim = base.clamp01((breakup - .48) / .52)
                start += trim * rng.uniform(.02, .18)
                end -= trim * rng.uniform(.05, .24)
            if end - start < .16:
                continue
            off = rng.uniform(omin, omax)
            phase, freq = rng.uniform(0, math.tau), rng.uniform(.72, 1.85)
            width = rng.uniform(wmin, wmax)
            pts, ws = [], []
            for i in range(56):
                q = i / 55.0
                u = start + (end - start) * q
                x, y, a = point_on_spine(radius, tail + (head - tail) * u, p)
                nx, ny = math.cos(a), math.sin(a); tx, ty = -math.sin(a), math.cos(a)
                wave = .12 * math.sin(math.tau * freq * q + phase) + .04 * math.sin(math.tau * 2.3 * q + phase * .4)
                x += nx * nominal * (off + wave) + tx * nominal * .04 * math.sin(math.tau * 1.3 * q + phase)
                y += ny * nominal * (off + wave) + ty * nominal * .04 * math.sin(math.tau * 1.3 * q + phase)
                env = base.smoothstep(q / .08) * base.smoothstep((1.0 - q) / .07)
                pts.append((x, y)); ws.append(max(.0015, nominal * width * env * (1.0 + .22 * math.sin(math.tau * 1.8 * q + phase))))
            if (tier, stroke) in plumes and breakup < .48 and energy > .60:
                extend_end = stroke % 2 == 1
                ai, au = (-1, end) if extend_end else (0, start)
                _, _, a = point_on_spine(radius, tail + (head - tail) * au, p)
                tx, ty = -math.sin(a), math.cos(a)
                if not extend_end: tx, ty = -tx, -ty
                px, py = -ty, tx
                anchor = pts[ai]
                length = radius * float(p["shape.tongue_length"]) * rng.uniform(1.02, 1.60) * (.76 + .30 * energy)
                rootw = max(ws[ai], nominal * width * .42)
                ep, ew = [], []
                sign = -1.0 if stroke % 3 == 0 else 1.0
                for step in range(1, 12):
                    q = step / 11.0
                    bend = sign * math.sin(math.pi * q) * length * .09
                    ep.append((anchor[0] + tx * length * q + px * bend, anchor[1] + ty * length * q + py * bend))
                    ew.append(max(.0012, rootw * ((1.0 - q) ** 1.48)))
                if extend_end: pts += ep; ws += ew
                else: pts = list(reversed(ep)) + pts; ws = list(reversed(ew)) + ws
            z = .33 if tier == "outer" else .40 if tier == "body" else .51
            if tier != "inner":
                glow = materials["outer_glow"] if tier == "outer" else materials["body_glow"]
                base.add_curve(f"{prefix}_{tier}_flow_glow_{stroke}", pts, [w * 1.6 for w in ws], glow, layers["PLASMA"], z=z - .025, frame=index + 1, frames=frames)
            base.add_curve(f"{prefix}_{tier}_flow_{stroke}", pts, ws, mat, coll, z=z, frame=index + 1, frames=frames)


def add_hot_core(prefix, p, radius, tail, head, energy, materials, layers, seed, index, frames, breakup):
    nominal = float(p["thickness"]) * float(p["shape.body_scale"])
    heat = base.smoothstep((energy - .60) / .40)
    late = max(0.0, 1.0 - max(0.0, breakup - .20) * 1.65)
    if heat < .03 or late < .04 or breakup > .78:
        return
    for stroke, (off, width0) in enumerate(zip((-.40, -.30, -.20, -.10), (.040, .052, .045, .036))):
        rng = random.Random(seed * 900001 + stroke * 611 + index * 3571)
        phase, freq = rng.uniform(0, math.tau), rng.uniform(1.4, 2.8)
        pts, ws = [], []
        for i in range(86):
            q = i / 85.0
            x, y, a = point_on_spine(radius, tail + (head - tail) * q, p)
            nx, ny = math.cos(a), math.sin(a); tx, ty = -math.sin(a), math.cos(a)
            local = off + .16 * math.sin(math.tau * freq * q + phase) + .06 * math.sin(math.tau * freq * .43 * q + phase * .37)
            x += nx * nominal * local + tx * nominal * .065 * math.sin(math.tau * 3.2 * q + phase)
            y += ny * nominal * local + ty * nominal * .065 * math.sin(math.tau * 3.2 * q + phase)
            mod = 1.0 + .42 * math.sin(math.tau * 2.15 * q + phase)
            for pinch in (.24 + stroke * .045, .52 + stroke * .028, .75 - stroke * .026):
                d = abs(q - pinch)
                if d < .052: mod *= .13 + .87 * d / .052
            pts.append((x, y)); ws.append(max(.0013, nominal * width0 * max(.10, mod) * heat * late))
        chunks, cp, cw = [], [], []
        for i, (pt, w) in enumerate(zip(pts, ws)):
            q = i / 85.0
            gap = (stroke % 2 == 0 and .46 < q < .50) or (stroke % 2 == 1 and .70 < q < .735)
            if gap:
                if len(cp) >= 2: chunks.append((cp, cw))
                cp, cw = [], []
            else: cp.append(pt); cw.append(w)
        if len(cp) >= 2: chunks.append((cp, cw))
        for ci, (cpts, cws) in enumerate(chunks):
            base.add_curve(f"{prefix}_core_cyan_{stroke}_{ci}", cpts, [w * 2.1 for w in cws], materials["inner_glow"], layers["PLASMA"], z=.57, frame=index + 1, frames=frames)
            base.add_curve(f"{prefix}_core_white_{stroke}_{ci}", cpts, cws, materials["core"], layers["CORE"], z=.63, frame=index + 1, frames=frames)


def add_ignition(prefix, p, radius, materials, layers, seed, index, frames):
    x, y, a = point_on_spine(radius, .055, p)
    tx, ty = -math.sin(a), math.cos(a); nx, ny = math.cos(a), math.sin(a)
    for li, (tr, nr, mat, z) in enumerate(((.34, .50, materials["outer_glow"], .04), (.29, .43, materials["outer"], .10), (.22, .34, materials["body"], .16), (.09, .17, materials["inner"], .28))):
        rng = random.Random(seed + li * 131)
        p1, p2 = rng.uniform(0, math.tau), rng.uniform(0, math.tau)
        loop = []
        for k in range(22):
            aa = math.tau * k / 22.0
            wobble = 1.0 + .16 * math.sin(3 * aa + p1) + .10 * math.sin(5 * aa + p2)
            loop.append((x + tx * radius * tr * wobble * math.cos(aa) + nx * radius * nr * math.sin(aa), y + ty * radius * tr * wobble * math.cos(aa) + ny * radius * nr * math.sin(aa)))
        base.add_polygon(f"{prefix}_ignition_{li}", loop, mat, layers["PLASMA"] if li == 0 else layers["BODY"], z=z, frame=index + 1, frames=frames)


def add_fragments(prefix, removed, p, materials, layers, radius, seed, index, frames, breakup):
    progress = base.dissolve_progress(p, index, frames)
    if progress <= 0.0 or not removed: return
    rng = random.Random(seed * 49979687 + index * 8191 + 421)
    for frag in range(round(int(p["dissolve.fragment_count"]) * progress * 2.5)):
        x, y, tx, ty, nx, ny, width, erase, tier = removed[rng.randrange(len(removed))]
        drift = radius * float(p["dissolve.fragment_drift"]) * progress * rng.uniform(.3, 1.4) * (-1 if rng.random() < .5 else 1)
        x += nx * drift + tx * drift * rng.uniform(-.35, .22); y += ny * drift + ty * drift * rng.uniform(-.35, .22)
        size = max(radius * .0048, radius * float(p["dissolve.fragment_size"]) * rng.uniform(.09, .22))
        sides = 3 if frag % 3 else 4
        pts = [(x + math.cos(math.tau * k / sides + rng.uniform(-.15, .15)) * size * rng.uniform(.55, 1.0), y + math.sin(math.tau * k / sides + rng.uniform(-.15, .15)) * size * rng.uniform(.55, 1.0)) for k in range(sides)]
        mat = materials["body"] if rng.random() < .72 else materials["outer"]
        base.add_polygon(f"{prefix}_fragment_{frag}", pts, mat, layers["DISSOLVE"], z=.84, frame=index + 1, frames=frames)


def build_frame(spec, index, materials, layers):
    p, radius, frames, seed = spec["params"], float(spec["params"]["radius"]), int(spec["frames"]), int(spec["seed"])
    tail, head, energy, breakup = v6.motion_window(index, frames, float(p["timing.peak"]))
    prefix = f"F{index + 1:02d}"
    if index == 0:
        add_ignition(prefix, p, radius, materials, layers, seed, index, frames)
        return
    removed = []
    removed += v7.add_ribbon(prefix + "_outer_haze", "body", p, radius, tail, head, materials["outer_glow"], layers["PLASMA"], seed, index, frames, .02, 5.70, .78, 1.12)
    removed += v7.add_ribbon(prefix + "_outer", "body", p, radius, tail, head, materials["outer"], layers["BODY"], seed, index, frames, .08, 4.65, .58, 1.05)
    removed += v7.add_ribbon(prefix + "_body", "body", p, radius, tail, head, materials["body"], layers["BODY"], seed + 31, index, frames, .14, 2.65, .34, .92)
    removed += v7.add_ribbon(prefix + "_inner", "inner", p, radius, tail, head, materials["inner"], layers["BODY"], seed + 47, index, frames, .28, .22, .075, .52)
    add_flow_bundle(prefix, p, radius, tail, head, energy, materials, layers, seed, index, frames, breakup)
    add_hot_core(prefix, p, radius, tail, head, energy, materials, layers, seed, index, frames, breakup)
    v7.add_lightning(prefix, p, radius, tail, head, energy, breakup, materials, layers, seed, index, frames)
    add_fragments(prefix, removed, p, materials, layers, radius, seed, index, frames, breakup)


def embed_sources(spec):
    _base_embed_sources(spec)
    for filename in ("native_generate_vfx_v6.py", "native_generate_vfx_v7.py", "native_generate_vfx_v8.py"):
        try:
            text = bpy.data.texts.new("SOURCE_" + filename)
            text.write(Path(__file__).with_name(filename).read_text(encoding="utf-8"))
        except OSError:
            pass


v7.point_on_spine = point_on_spine
v7._macro_width = macro_width
v7._tri_visibility = tri_visibility
base.point_on_arc = point_on_spine
base.motion_window = v6.motion_window
base.setup_scene = setup_scene
base.make_materials = make_materials
base.add_ribbon = v7.add_ribbon
base.add_fragments = add_fragments
base.build_frame = build_frame
base.embed_sources = embed_sources

if __name__ == "__main__":
    base.main()
