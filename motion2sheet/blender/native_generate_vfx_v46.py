"""Blender-native VFX renderer V46: organic curved terminal decay arcs."""
from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path

import bpy

_V45_PATH = Path(__file__).with_name("native_generate_vfx_v45.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v45", _V45_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load V45")
v45 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v45)

v44 = v45.v44
v43 = v44.v43
v42 = v43.v42
v41 = v42.v41
v40 = v41.v40
v16, base = v40.v16, v40.base
_ORIG_MEMORY = v40.add_motion_memory


def setup_scene(spec):
    scene, layers = v45.setup_scene(spec)
    scene["vfx_renderer"] = "blender-native-v46"
    scene["vfx_decay_memory_model"] = "organic-curved-tapered-residual-arcs"
    return scene, layers


def _add_decay_arcs(prefix, p, radius, materials, layers, seed, index, frames):
    if index not in (frames - 2, frames - 1):
        return

    nominal = float(p["thickness"]) * float(p["shape.body_scale"])
    final = index == frames - 1
    count = 5 if final else 8

    # Deterministic centers bias toward the same curved motion path rather than
    # a random explosion. Different spans/lanes create islands with motion memory.
    for ai in range(count):
        rng = random.Random(seed * 86028121 + index * 65537 + ai * 12289)
        center = rng.uniform(.10, .91)
        span = rng.uniform(.055, .125) if final else rng.uniform(.075, .165)
        start = max(.02, center - span * .5)
        end = min(.98, center + span * .5)
        lane = nominal * rng.uniform(-.42, 1.25)
        drift = radius * rng.uniform(-.030, .055) * (1.20 if final else .86)
        phase = rng.uniform(0.0, math.tau)
        steps = rng.randint(10, 15)
        rootw = nominal * rng.uniform(.060, .145) * (.72 if final else 1.0)
        pts, widths = [], []

        for j in range(steps):
            q = j / (steps - 1)
            u = start + (end - start) * q
            x, y, a = v16.point_on_spine(radius, u, p)
            nx, ny = math.cos(a), math.sin(a)
            tx, ty = -math.sin(a), math.cos(a)

            local_lane = lane + nominal * .16 * math.sin(math.pi * q + phase)
            local_drift = drift * (q - .5) + nominal * .050 * math.sin(math.tau * 1.20 * q + phase * .51)
            x += nx * local_lane + tx * local_drift
            y += ny * local_lane + ty * local_drift
            pts.append((x, y))

            env = math.sin(math.pi * q) ** .52
            taper = (.70 + .30 * (1.0 - q)) if ai % 2 else (.74 + .26 * q)
            pulse = .82 + .20 * math.sin(math.tau * 1.15 * q + phase)
            widths.append(max(.0010, rootw * env * taper * pulse))

        hot = (not final) and ai < 2
        cyan = hot or ai % 3 == 0
        if hot:
            mat, glow = materials["core"], materials["core_glow"]
            wm, gm = .60, 2.35
        elif cyan:
            mat, glow = materials["inner"], materials["inner_glow"]
            wm, gm = .88, 2.10
        else:
            mat, glow = materials["body"], materials["body_glow"]
            wm, gm = 1.0, 1.80

        body_widths = [w * wm for w in widths]
        base.add_curve(
            f"{prefix}_decay_arc_glow_{ai}", pts,
            [w * gm for w in body_widths], glow, layers["PLASMA"],
            z=.59, frame=index + 1, frames=frames,
        )
        base.add_curve(
            f"{prefix}_decay_arc_{ai}", pts, body_widths, mat,
            layers["WISPS"], z=.69, frame=index + 1, frames=frames,
        )

    # A few tiny curved hooks detach from the main islands. Keep them short so
    # the final frame reads as residual motion, not a particle burst.
    hooks = 4 if final else 6
    for hi in range(hooks):
        rng = random.Random(seed * 104729 + index * 32771 + hi * 4099)
        u = rng.uniform(.14, .88)
        x, y, a = v16.point_on_spine(radius, u, p)
        nx, ny = math.cos(a), math.sin(a)
        tx, ty = -math.sin(a), math.cos(a)
        x += nx * nominal * rng.uniform(-.55, 1.40)
        y += ny * nominal * rng.uniform(-.55, 1.40)
        length = radius * rng.uniform(.025, .065) * (.78 if final else 1.0)
        side = rng.uniform(-.22, .22)
        pts, widths = [], []
        for j in range(7):
            q = j / 6.0
            pts.append((
                x + tx * length * q + nx * length * side * math.sin(math.pi * q),
                y + ty * length * q + ny * length * side * math.sin(math.pi * q),
            ))
            widths.append(max(.0008, nominal * rng.uniform(.018, .032) * math.sin(math.pi * q) ** .55))
        base.add_curve(
            f"{prefix}_decay_hook_{hi}", pts, widths, materials["inner"],
            layers["WISPS"], z=.71, frame=index + 1, frames=frames,
        )


def add_motion_memory(prefix, p, radius, materials, layers, seed, index, frames):
    _ORIG_MEMORY(prefix, p, radius, materials, layers, seed, index, frames)
    _add_decay_arcs(prefix, p, radius, materials, layers, seed + 130363, index, frames)


def embed_sources(spec):
    v45.embed_sources(spec)
    try:
        text = bpy.data.texts.new("SOURCE_native_generate_vfx_v46.py")
        text.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError:
        pass

v40.add_motion_memory = add_motion_memory
base.setup_scene = setup_scene
base.embed_sources = embed_sources

if __name__ == "__main__":
    base.main()
