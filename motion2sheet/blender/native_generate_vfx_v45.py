"""Blender-native VFX renderer V45: broad tapered terminal energy tongues."""
from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path

import bpy

_V44_PATH = Path(__file__).with_name("native_generate_vfx_v44.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v44", _V44_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load V44")
v44 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v44)

base = v44.base
_ORIG_TERMINAL_STREAKS = v44.add_terminal_streaks


def setup_scene(spec):
    scene, layers = v44.setup_scene(spec)
    scene["vfx_renderer"] = "blender-native-v45"
    scene["vfx_terminal_mass_model"] = "broad-tapered-blue-cyan-growth-tongues"
    return scene, layers


def _broad_growth_tongues(prefix, p, radius, tail, energy, materials, layers, seed, index, frames):
    nominal = float(p["thickness"]) * float(p["shape.body_scale"])
    progression = {1: .78, 2: .94, 3: 1.08, 4: 1.20}.get(index, 1.0)
    count = 5 if index < 4 else 6

    for ti in range(count):
        rng = random.Random(seed * 49979687 + index * 65537 + ti * 12289)
        x, y, nx, ny, tx, ty = v44._basis(radius, tail, p)

        # Roots are distributed across the outer half of the terminal mass.
        # Broad roots plus strong taper create flame-like tongues instead of
        # the thin wire/whisker look from V44's fine directional streaks.
        side = nominal * rng.uniform(.05, 1.22)
        x += nx * side
        y += ny * side
        length = radius * rng.uniform(.16, .33) * progression * (.88 + .18 * energy)
        if ti in (1, 4):
            length *= rng.uniform(1.18, 1.38)
        bend = rng.uniform(-.13, .17)
        phase = rng.uniform(0.0, math.tau)
        rootw = nominal * rng.uniform(.105, .205)
        steps = 18
        pts, widths = [], []

        for j in range(steps):
            q = j / (steps - 1)
            d = length * q
            side_curve = length * bend * math.sin(math.pi * q)
            flutter = length * .022 * math.sin(math.tau * 1.45 * q + phase) * math.sin(math.pi * q)
            pts.append((
                x + tx * d + nx * (side_curve + flutter),
                y + ty * d + ny * (side_curve + flutter),
            ))
            # Thick embedded root, then fast flame taper with a slight middle
            # pulse so the tongue reads as energy mass rather than a triangle.
            taper = max(.012, (1.0 - q) ** 1.12)
            pulse = .88 + .16 * math.sin(math.pi * q) + .08 * math.sin(math.tau * 2.0 * q + phase)
            widths.append(max(.0012, rootw * taper * pulse))

        cyan = ti in (0, 3)
        body = materials["inner"] if cyan else materials["body"]
        glow = materials["inner_glow"] if cyan else materials["body_glow"]
        base.add_curve(
            f"{prefix}_broad_growth_glow_{ti}", pts,
            [w * (2.05 if cyan else 1.72) for w in widths], glow,
            layers["PLASMA"], z=.45, frame=index + 1, frames=frames,
        )
        base.add_curve(
            f"{prefix}_broad_growth_{ti}", pts, widths, body,
            layers["BODY"], z=.53, frame=index + 1, frames=frames,
        )


def add_terminal_streaks(prefix, p, radius, tail, head, energy,
                         materials, layers, seed, index, frames, breakup):
    _ORIG_TERMINAL_STREAKS(
        prefix, p, radius, tail, head, energy,
        materials, layers, seed, index, frames, breakup,
    )
    if index < 1 or index > 4 or breakup > .32:
        return
    _broad_growth_tongues(
        prefix, p, radius, tail, energy, materials, layers,
        seed + 104729, index, frames,
    )


def embed_sources(spec):
    v44.embed_sources(spec)
    try:
        text = bpy.data.texts.new("SOURCE_native_generate_vfx_v45.py")
        text.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError:
        pass

v44.add_terminal_streaks = add_terminal_streaks
base.setup_scene = setup_scene
base.embed_sources = embed_sources

if __name__ == "__main__":
    base.main()
