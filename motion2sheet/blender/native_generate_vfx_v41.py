"""Blender-native VFX renderer V41: stronger irregular white-hot core energy mass."""
from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path

import bpy

_V40_PATH = Path(__file__).with_name("native_generate_vfx_v40.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v40", _V40_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load V40")
v40 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v40)

v39, v38, v37 = v40.v39, v40.v38, v40.v37
v36, v35, v33, v32, v29, v27, v23 = v40.v36, v40.v35, v40.v33, v40.v32, v40.v29, v40.v27, v40.v23
v21, v18, v17, v16, v14 = v40.v21, v40.v18, v40.v17, v40.v16, v40.v14
v9, v8, v7, v6, base = v40.v9, v40.v8, v40.v7, v40.v6, v40.base


def setup_scene(spec):
    scene, layers = v40.setup_scene(spec)
    scene["vfx_renderer"] = "blender-native-v41"
    scene["vfx_core_model"] = "v33-segmented-core-plus-broad-irregular-hot-lobes"
    scene["vfx_core_mass_boost"] = 1.0
    return scene, layers


def _add_chunked_curve(prefix, points, widths, materials, layers, index, frames, zbase):
    """Render one reinforced lobe with two tiny cyan breathing gaps."""
    samples = len(points)
    chunks = []
    cp, cw = [], []
    for i, (pt, width) in enumerate(zip(points, widths)):
        q = i / max(1, samples - 1)
        gap = abs(q - .39) < .012 or abs(q - .73) < .010
        if gap:
            if len(cp) >= 4:
                chunks.append((cp, cw))
            cp, cw = [], []
        else:
            cp.append(pt)
            cw.append(width)
    if len(cp) >= 4:
        chunks.append((cp, cw))

    for ci, (pp, ww) in enumerate(chunks):
        # A much broader cyan plasma bed carries the energy mass; white stays
        # inside it so the result reads hot and heavy without becoming a slab.
        base.add_curve(
            f"{prefix}_mass_cyan_{ci}", pp, [w * 3.35 for w in ww],
            materials["inner_glow"], layers["PLASMA"], z=zbase,
            frame=index + 1, frames=frames,
        )
        base.add_curve(
            f"{prefix}_mass_hotglow_{ci}", pp, [w * 1.80 for w in ww],
            materials["core_glow"], layers["PLASMA"], z=zbase + .045,
            frame=index + 1, frames=frames,
        )
        base.add_curve(
            f"{prefix}_mass_hot_{ci}", pp, [w * .90 for w in ww],
            materials["core"], layers["CORE"], z=zbase + .095,
            frame=index + 1, frames=frames,
        )


def add_core(prefix, p, radius, tail, head, energy, materials, layers, seed, index, frames, breakup):
    # Preserve the V33 segmented core that already solved the white-slab issue.
    v33.add_core(prefix, p, radius, tail, head, energy, materials, layers, seed, index, frames, breakup)

    heat = base.smoothstep((energy - .36) / .64)
    if heat < .025 or breakup > .70:
        return

    nominal = float(p["thickness"]) * float(p["shape.body_scale"])
    ratio = float(p["core.streak_width_ratio"])
    center_jitter = float(p["core.center_jitter"]) / max(1.0, float(p["core.width_max"]))

    # Four partially-overlapping hot lobes. Compared with V33 they are wider,
    # sit at different lanes through the plasma body, and carry a much broader
    # cyan support layer. This is intentionally a mass boost, not more outline.
    lobes = (
        (.035, .36, .22),
        (.22, .57, .40),
        (.43, .79, .28),
        (.66, .985, .46),
    )
    strength = .72 + .42 * heat

    for li, (start0, end0, lane0) in enumerate(lobes):
        rng = random.Random(seed * 15485863 + index * 65537 + li * 12289)
        start = base.clamp01(start0 + rng.uniform(-.014, .014))
        end = base.clamp01(end0 + rng.uniform(-.014, .014))
        lane = lane0 + rng.uniform(-.045, .045)
        phase = rng.uniform(0.0, math.tau)
        freq = rng.uniform(1.15, 2.05)
        samples = 76
        points, widths = [], []

        for i in range(samples):
            q = i / (samples - 1)
            local = start + (end - start) * q
            x, y, a = v16.point_on_spine(radius, tail + (head - tail) * local, p)
            nx, ny = math.cos(a), math.sin(a)
            tx, ty = -math.sin(a), math.cos(a)

            lateral = lane
            lateral += center_jitter * (
                .34 * math.sin(math.tau * freq * q + phase)
                + .15 * math.sin(math.tau * 3.6 * q + phase * .41)
            )
            tangent_wobble = nominal * (
                .050 * math.sin(math.tau * 1.75 * q + phase * .73)
                + .018 * math.sin(math.tau * 4.2 * q + phase)
            )
            x += nx * nominal * lateral + tx * tangent_wobble
            y += ny * nominal * lateral + ty * tangent_wobble

            env = math.sin(math.pi * q) ** .30
            pulse = (
                .90
                + .20 * math.sin(math.tau * (1.22 + .11 * li) * q + phase)
                + .10 * math.sin(math.tau * 3.4 * q + phase * .37)
            )
            pinch = 1.0
            for pc, depth, span in ((.24, .52, .055), (.58, .38, .047), (.84, .58, .040)):
                d = abs(q - (pc + .012 * (li % 2)))
                if d < span:
                    pinch *= depth + (1.0 - depth) * d / span

            # Typical reinforced hot lobe is ~1.7x the V33 hot width before
            # the original V33 streak underneath is counted.
            width = nominal * ratio * rng.uniform(.78, 1.02)
            width *= heat * strength * env * max(.34, pulse) * pinch
            points.append((x, y))
            widths.append(max(.0022, width))

        _add_chunked_curve(
            f"{prefix}_core_mass_{li}", points, widths,
            materials, layers, index, frames, .555 + li * .002,
        )


def embed_sources(spec):
    v40.embed_sources(spec)
    try:
        text = bpy.data.texts.new("SOURCE_native_generate_vfx_v41.py")
        text.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError:
        pass

# Preserve every verified V40 decision; only replace the core energy renderer.
v18.add_core = add_core
base.setup_scene = setup_scene
base.embed_sources = embed_sources

if __name__ == "__main__":
    base.main()
