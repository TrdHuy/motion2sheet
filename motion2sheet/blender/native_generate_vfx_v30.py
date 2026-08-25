"""Blender-native VFX renderer V30: directional ignition bridge and shell-first F6 erosion."""
from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path

import bpy

_V29_PATH = Path(__file__).with_name("native_generate_vfx_v29.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v29", _V29_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load V29")
v29 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v29)

v28, v27, v23 = v29.v28, v29.v27, v29.v23
v21, v19, v18, v17, v16, v14 = v29.v21, v29.v19, v29.v18, v29.v17, v29.v16, v29.v14
v12, v9, v8, v7, v6, base = v29.v12, v29.v9, v29.v8, v29.v7, v29.v6, v29.base


def setup_scene(spec):
    scene, layers = v29.setup_scene(spec)
    scene["vfx_renderer"] = "blender-native-v30"
    scene["vfx_f1_f2_continuity"] = "starburst-plus-directional-seed-blade"
    scene["vfx_f6_transition"] = "outer-shell-peel-with-protected-inner-core"
    return scene, layers


def add_ignition(prefix, p, radius, materials, layers, seed, index, frames):
    # Keep the energetic starburst from V28, then add a short piece of the real
    # slash spine so F1 visibly points into the geometry that appears in F2.
    v28.add_ignition(prefix, p, radius, materials, layers, seed, index, frames)
    nominal = float(p["thickness"]) * float(p["shape.body_scale"])
    rng = random.Random(seed * 510071 + 301)
    pts = []
    widths = []
    n = 30
    for i in range(n):
        q = i / (n - 1)
        u = .55 - .145 * q
        x, y, a = v16.point_on_spine(radius, u, p)
        nx, ny = math.cos(a), math.sin(a)
        tx, ty = -math.sin(a), math.cos(a)
        wiggle = nominal * (.035 * math.sin(math.tau * 1.25 * q + .6) + .012 * math.sin(math.tau * 3.1 * q + 1.7))
        x += nx * wiggle + tx * nominal * .012 * math.sin(math.pi * q)
        y += ny * wiggle + ty * nominal * .012 * math.sin(math.pi * q)
        env = (1.0 - q) ** .42
        pulse = .90 + .12 * math.sin(math.tau * 1.4 * q + .4)
        widths.append(max(.002, nominal * .32 * env * pulse))
        pts.append((x, y))

    base.add_curve(f"{prefix}_seed_outer_glow", pts, [w * 4.2 for w in widths], materials["outer_glow"], layers["PLASMA"], z=.36, frame=index+1, frames=frames)
    base.add_curve(f"{prefix}_seed_body", pts, [w * 2.35 for w in widths], materials["body"], layers["BODY"], z=.43, frame=index+1, frames=frames)
    base.add_curve(f"{prefix}_seed_inner_glow", pts, [w * 1.62 for w in widths], materials["inner_glow"], layers["PLASMA"], z=.54, frame=index+1, frames=frames)
    base.add_curve(f"{prefix}_seed_inner", pts, [w * 1.05 for w in widths], materials["inner"], layers["CORE"], z=.61, frame=index+1, frames=frames)
    base.add_curve(f"{prefix}_seed_hot", pts, [w * .50 for w in widths], materials["core"], layers["CORE"], z=.70, frame=index+1, frames=frames)

    # Two restrained side wisps make the seed feel like plasma rather than a
    # rigid painted stroke, while preserving a clear growth direction.
    for wi, sign in enumerate((-1.0, 1.0)):
        wpts = []
        wws = []
        phase = rng.uniform(0.0, math.tau)
        for i in range(18):
            q = i / 17.0
            u = .545 - .115 * q
            x, y, a = v16.point_on_spine(radius, u, p)
            nx, ny = math.cos(a), math.sin(a)
            off = sign * nominal * (.32 + .10 * math.sin(math.pi * q + phase)) * math.sin(math.pi * q)
            x += nx * off
            y += ny * off
            wpts.append((x, y))
            wws.append(max(.0013, nominal * .055 * ((1.0 - q) ** 1.15)))
        base.add_curve(f"{prefix}_seed_wisp_glow_{wi}", wpts, [w * 2.0 for w in wws], materials["body_glow"], layers["PLASMA"], z=.50, frame=index+1, frames=frames)
        base.add_curve(f"{prefix}_seed_wisp_{wi}", wpts, wws, materials["body"], layers["WISPS"], z=.57, frame=index+1, frames=frames)


def tri_visibility(u, v, tier, p, seed, index, frames, tri):
    if index != frames - 3:
        return v29.tri_visibility(u, v, tier, p, seed, index, frames, tri)
    # F6 is only the onset of breakup. Protect the inner ribbon entirely and
    # open compact holes on the outer half of the blue shell. Because the two
    # body ribbons use different deterministic seeds, one layer often reveals
    # the next instead of producing a harsh black cut through the hot core.
    if tier != "body":
        return 1.0
    rng = random.Random(seed * 32452843 + 2801)
    best = 99.0
    for ci in range(2):
        cu = rng.uniform(.24, .78)
        cv = rng.uniform(.62, .90)
        ru = rng.uniform(.045, .075)
        rv = rng.uniform(.050, .085)
        ang = rng.uniform(-.75, .75)
        ca, sa = math.cos(ang), math.sin(ang)
        du, dv = u - cu, v - cv
        xu = du * ca + dv * sa
        yv = -du * sa + dv * ca
        d = (xu / ru) ** 2 + (yv / rv) ** 2
        phase = rng.uniform(0.0, math.tau)
        edge = .10 * math.sin(math.tau * (3.7 * u + 2.4 * v) + phase)
        edge += .04 * math.sin(math.tau * (8.2 * u - 3.8 * v) + phase * .43)
        best = min(best, d + edge)
    return 0.0 if best < .72 else 1.0


def embed_sources(spec):
    v29.embed_sources(spec)
    try:
        text = bpy.data.texts.new("SOURCE_native_generate_vfx_v30.py")
        text.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError:
        pass

# V29's high-resolution F6 mesh calls its module-global tri_visibility name.
v29.tri_visibility = tri_visibility
v9.tri_visibility = tri_visibility
v9.add_ribbon = v29.add_ribbon
v8.add_fragments = v29.add_fragments
v9.add_ignition = add_ignition
v21.add_lightning = v28.add_lightning
v6.motion_window = v27.motion_window
v18.add_core = v27.add_core
v17._band_polygon = v19._band_polygon
v12.point_on_spine = v16.point_on_spine; v9.point_on_spine = v16.point_on_spine; v8.point_on_spine = v16.point_on_spine; v7.point_on_spine = v16.point_on_spine; base.point_on_arc = v16.point_on_spine
base.setup_scene = setup_scene; base.make_materials = v14.make_materials; base.build_frame = v23.build_frame; base.embed_sources = embed_sources

if __name__ == "__main__":
    base.main()
