"""Blender-native VFX renderer V33: segmented white-hot core polish."""
from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path

import bpy

_V32_PATH = Path(__file__).with_name("native_generate_vfx_v32.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v32", _V32_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load V32")
v32 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v32)

v31, v30, v29, v28, v27, v23 = v32.v31, v32.v30, v32.v29, v32.v28, v32.v27, v32.v23
v21, v19, v18, v17, v16, v14 = v32.v21, v32.v19, v32.v18, v32.v17, v32.v16, v32.v14
v12, v9, v8, v7, v6, base = v32.v12, v32.v9, v32.v8, v32.v7, v32.v6, v32.base


def setup_scene(spec):
    scene, layers = v32.setup_scene(spec)
    scene["vfx_renderer"] = "blender-native-v33"
    scene["vfx_core_model"] = "four-staggered-hot-streaks-with-cyan-gaps"
    return scene, layers


def add_core(prefix, p, radius, tail, head, energy, materials, layers, seed, index, frames, breakup):
    heat = base.smoothstep((energy - .40) / .60)
    if heat < .02 or breakup > .70:
        return
    nominal = float(p["thickness"]) * float(p["shape.body_scale"])
    ratio = float(p["core.streak_width_ratio"])
    wj = float(p["core.width_jitter"])
    center_jitter = float(p["core.center_jitter"]) / max(1.0, float(p["core.width_max"]))

    # Stagger the major white-hot streaks along the arc instead of drawing
    # five almost-full-length overlapping lines. This keeps the core strong
    # and thick locally while allowing visible cyan breathing gaps.
    spans = ((.035, .43), (.20, .63), (.43, .83), (.66, .975))
    for s, (start0, end0) in enumerate(spans):
        rng = random.Random(seed * 760001 + s * 9209 + index * 3571)
        start = base.clamp01(start0 + rng.uniform(-.018, .018))
        end = base.clamp01(end0 + rng.uniform(-.018, .018))
        lane = .30 + .072 * s + rng.uniform(-.035, .035)
        phase = rng.uniform(0.0, math.tau)
        freq = rng.uniform(1.35, 2.45)
        points, widths = [], []
        samples = 72
        for i in range(samples):
            q = i / (samples - 1)
            local = start + (end - start) * q
            x, y, a = v16.point_on_spine(radius, tail + (head - tail) * local, p)
            nx, ny = math.cos(a), math.sin(a)
            tx, ty = -math.sin(a), math.cos(a)
            off = lane + center_jitter * (.42 * math.sin(math.tau * freq * q + phase) + .18 * math.sin(math.tau * 3.25 * q + phase * .43))
            x += nx * nominal * off + tx * nominal * .045 * math.sin(math.tau * 2.15 * q + phase)
            y += ny * nominal * off + ty * nominal * .045 * math.sin(math.tau * 2.15 * q + phase)
            env = math.sin(math.pi * q) ** .25
            pulse = .82 + .23 * math.sin(math.tau * (1.38 + .13 * s) * q + phase) + .08 * math.sin(math.tau * 4.0 * q + phase * .37)
            pinch = 1.0
            for pc in (.29 + .018 * (s % 2), .66 - .012 * (s % 3)):
                d = abs(q - pc)
                if d < .050:
                    pinch *= .18 + .82 * d / .050
            width = nominal * ratio * rng.uniform(.48, .66) * env * pinch * max(.34, 1 + wj * .25 * math.sin(math.tau * 2.2 * q + phase)) * heat * pulse
            points.append((x, y)); widths.append(max(.0018, width))

        # A narrow deterministic split per streak prevents any one white line
        # from becoming a continuous outline, while cyan support bridges it.
        split_at = .52 + (.045 if s % 2 else -.035)
        chunks, cp, cw = [], [], []
        for i, (pt, width) in enumerate(zip(points, widths)):
            q = i / (samples - 1)
            if abs(q - split_at) < (.020 + .003 * s):
                if len(cp) >= 4:
                    chunks.append((cp, cw))
                cp, cw = [], []
            else:
                cp.append(pt); cw.append(width)
        if len(cp) >= 4:
            chunks.append((cp, cw))

        for ci, (pp, ww) in enumerate(chunks):
            base.add_curve(f"{prefix}_core_cyan_{s}_{ci}", pp, [w * 2.55 for w in ww], materials["inner_glow"], layers["PLASMA"], z=.565, frame=index+1, frames=frames)
            base.add_curve(f"{prefix}_core_glow_{s}_{ci}", pp, [w * 1.45 for w in ww], materials["core_glow"], layers["PLASMA"], z=.615, frame=index+1, frames=frames)
            base.add_curve(f"{prefix}_core_hot_{s}_{ci}", pp, ww, materials["core"], layers["CORE"], z=.67, frame=index+1, frames=frames)


def embed_sources(spec):
    v32.embed_sources(spec)
    try:
        text = bpy.data.texts.new("SOURCE_native_generate_vfx_v33.py")
        text.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError:
        pass

v29.tri_visibility = v32.tri_visibility
v9.tri_visibility = v32.tri_visibility
v9.add_ribbon = v29.add_ribbon
v8.add_fragments = v29.add_fragments
v9.add_ignition = v30.add_ignition
v21.add_lightning = v28.add_lightning
v6.motion_window = v27.motion_window
v18.add_core = add_core
v17._band_polygon = v19._band_polygon
v12.point_on_spine = v16.point_on_spine; v9.point_on_spine = v16.point_on_spine; v8.point_on_spine = v16.point_on_spine; v7.point_on_spine = v16.point_on_spine; base.point_on_arc = v16.point_on_spine
base.setup_scene = setup_scene; base.make_materials = v14.make_materials; base.build_frame = v23.build_frame; base.embed_sources = embed_sources

if __name__ == "__main__":
    base.main()
