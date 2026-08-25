"""Blender-native VFX renderer V44: elongated directional terminal streaks."""
from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path

import bpy

_V43_PATH = Path(__file__).with_name("native_generate_vfx_v43.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v43", _V43_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load V43")
v43 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v43)

v42, v41 = v43.v42, v43.v41
v40 = v41.v40
v16, v6, base = v40.v16, v40.v6, v40.base
_ORIG_BUILD_FRAME = base.build_frame


def setup_scene(spec):
    scene, layers = v43.setup_scene(spec)
    scene["vfx_renderer"] = "blender-native-v44"
    scene["vfx_terminal_streak_model"] = "directional-tapered-growth-and-origin-fans"
    return scene, layers


def _basis(radius, u, p):
    x, y, a = v16.point_on_spine(radius, base.clamp01(u), p)
    nx, ny = math.cos(a), math.sin(a)
    tx, ty = -math.sin(a), math.cos(a)
    return x, y, nx, ny, tx, ty


def _terminal_fan(prefix, p, radius, u, direction, count, length_scale,
                  materials, layers, seed, index, frames, hot_count):
    nominal = float(p["thickness"]) * float(p["shape.body_scale"])
    for si in range(count):
        rng = random.Random(seed * 32452843 + index * 65537 + si * 10009 + (17 if direction < 0 else 0))
        x, y, nx, ny, tx, ty = _basis(radius, u, p)

        # Fan mostly outside the plasma mass while keeping a few inner streaks.
        normal_off = nominal * rng.uniform(-.18, 1.35)
        x += nx * normal_off
        y += ny * normal_off

        length = radius * rng.uniform(.105, .285) * length_scale
        if si in (1, count - 2):
            length *= rng.uniform(1.28, 1.58)
        bend = rng.uniform(-.17, .20)
        phase = rng.uniform(0.0, math.tau)
        pts, widths = [], []
        steps = rng.randint(10, 15)
        rootw = nominal * rng.uniform(.030, .095)

        for j in range(steps):
            q = j / (steps - 1)
            # First ~20% stays embedded at the terminal, then extends sharply
            # in the true trajectory direction to form a readable motion tail.
            d = length * (q ** 1.05)
            side = length * bend * math.sin(math.pi * q) * (.35 + .65 * q)
            flutter = length * .018 * math.sin(math.tau * 1.65 * q + phase) * math.sin(math.pi * q)
            px = x + tx * direction * d + nx * (side + flutter)
            py = y + ty * direction * d + ny * (side + flutter)
            pts.append((px, py))
            env = max(.025, (1.0 - q) ** 1.28)
            pulse = .86 + .18 * math.sin(math.tau * 1.25 * q + phase)
            widths.append(max(.0009, rootw * env * pulse))

        hot = si < hot_count
        cyan = hot or si % 3 == 0
        if hot:
            mat, glow = materials["core"], materials["core_glow"]
            width_mult, glow_mult = .58, 2.45
        elif cyan:
            mat, glow = materials["inner"], materials["inner_glow"]
            width_mult, glow_mult = .82, 2.15
        else:
            mat, glow = materials["body"], materials["body_glow"]
            width_mult, glow_mult = 1.0, 1.85

        body_widths = [w * width_mult for w in widths]
        base.add_curve(
            f"{prefix}_terminal_glow_{direction}_{si}", pts,
            [w * glow_mult for w in body_widths], glow, layers["PLASMA"],
            z=.48, frame=index + 1, frames=frames,
        )
        base.add_curve(
            f"{prefix}_terminal_{direction}_{si}", pts, body_widths,
            mat, layers["WISPS"], z=.58 + (.07 if hot else 0.0),
            frame=index + 1, frames=frames,
        )


def add_terminal_streaks(prefix, p, radius, tail, head, energy,
                         materials, layers, seed, index, frames, breakup):
    # Only polish buildup/peak. Dissolve frames keep their independently tuned
    # V40 motion-memory topology.
    if index < 1 or index > 4 or breakup > .32:
        return

    progression = {1: .72, 2: .90, 3: 1.06, 4: 1.20}.get(index, 1.0)
    energy_scale = progression * (.82 + .22 * max(.0, min(1.0, energy)))

    # Growth tip: tail moves toward larger u from F2 to F5. Long, mostly blue/
    # cyan streamers make the live slash end sharp and directional.
    _terminal_fan(
        prefix + "_growth", p, radius, tail, +1.0,
        9, energy_scale, materials, layers, seed + 17011,
        index, frames, hot_count=2,
    )

    # Origin terminal: shorter counter-fan preserves the upper F1/F2 anchor
    # while avoiding the blunt rounded cap seen in earlier versions.
    _terminal_fan(
        prefix + "_origin", p, radius, head, -1.0,
        5, energy_scale * .62, materials, layers, seed + 7907,
        index, frames, hot_count=1,
    )


def build_frame(spec, index, materials, layers):
    _ORIG_BUILD_FRAME(spec, index, materials, layers)
    if index == 0:
        return
    p = spec["params"]
    frames = int(spec["frames"])
    radius = float(p["radius"])
    tail, head, energy, breakup = v6.motion_window(index, frames, float(p["timing.peak"]))
    add_terminal_streaks(
        f"F{index+1:02d}", p, radius, tail, head, energy,
        materials, layers, int(spec["seed"]), index, frames, breakup,
    )


def embed_sources(spec):
    v43.embed_sources(spec)
    try:
        text = bpy.data.texts.new("SOURCE_native_generate_vfx_v44.py")
        text.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError:
        pass

base.setup_scene = setup_scene
base.build_frame = build_frame
base.embed_sources = embed_sources

if __name__ == "__main__":
    base.main()
