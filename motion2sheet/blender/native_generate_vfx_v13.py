"""Blender-native VFX renderer V13: contract terminal breakup shards."""
from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path

import bpy

_V12_PATH = Path(__file__).with_name("native_generate_vfx_v12.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v12", _V12_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load Blender-native V12 renderer")
v12 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v12)
base, v6 = v12.base, v12.v6
_base_setup_scene = v12.setup_scene
_base_build_frame = v12.build_frame
_base_embed_sources = v12.embed_sources


def setup_scene(spec):
    scene, layers = _base_setup_scene(spec)
    scene["vfx_renderer"] = "blender-native-v13"
    scene["vfx_breakup_model"] = "contract-holes-plus-detached-terminal-shards"
    return scene, layers


def add_terminal_shards(prefix, p, radius, tail, head, materials, layers, seed, index, frames):
    """Create readable detached F8 remnants only when dissolve is active.

    These are not arbitrary sparks: each shard is sampled from the canonical
    slash trajectory, then pushed along local normal/tangent directions.  The
    result keeps the curved motion memory requested by the contract while
    making the terminal phase genuinely more fragmented than the powered
    baseline.
    """
    if float(p["dissolve.strength"]) <= 0.0 or index != frames - 1:
        return

    nominal = float(p["thickness"]) * float(p["shape.body_scale"])
    requested = max(6, min(14, int(p["dissolve.fragment_count"]) // 3))
    spread = float(p["dissolve.fragment_spread"])
    drift = float(p["dissolve.fragment_drift"])
    size_ctl = float(p["dissolve.fragment_size"])

    for shard in range(requested):
        rng = random.Random(seed * 170003 + shard * 7907 + 31)
        local = rng.uniform(.10, .91)
        u = tail + (head - tail) * local
        x, y, a = v12.point_on_spine(radius, u, p)
        nx, ny = math.cos(a), math.sin(a)
        tx, ty = -math.sin(a), math.cos(a)

        # Alternate both sides of the slash and move fragments away from the
        # surviving body so connected-component semantics match visible breakup.
        side = -1.0 if shard % 2 == 0 else 1.0
        normal_push = radius * (0.085 + rng.uniform(.025, .105)) * spread * side
        tangent_push = radius * rng.uniform(-.070, .095) * (0.55 + drift * 2.0)
        x += nx * normal_push + tx * tangent_push
        y += ny * normal_push + ty * tangent_push

        length = radius * (0.040 + rng.uniform(.020, .055)) * (0.75 + size_ctl * 3.0)
        bend = side * length * rng.uniform(.08, .20)
        pts = [
            (x - tx * length * .45, y - ty * length * .45),
            (x + nx * bend, y + ny * bend),
            (x + tx * length * .55 + nx * bend * .25, y + ty * length * .55 + ny * bend * .25),
        ]
        rootw = max(.0020, nominal * rng.uniform(.025, .050))
        widths = [rootw * .55, rootw, .0012]
        mat = materials["body"] if shard % 3 else materials["outer"]
        base.add_curve(
            f"{prefix}_terminal_shard_{shard}", pts, widths, mat,
            layers["WISPS"], z=.46 + shard * .0005,
            frame=index + 1, frames=frames,
        )


def build_frame(spec, index, materials, layers):
    _base_build_frame(spec, index, materials, layers)
    p = spec["params"]
    frames = int(spec["frames"])
    if index != frames - 1:
        return
    radius = float(p["radius"])
    seed = int(spec["seed"])
    tail, head, _energy, _breakup = v6.motion_window(index, frames, float(p["timing.peak"]))
    add_terminal_shards(f"F{index+1:02d}", p, radius, tail, head, materials, layers, seed, index, frames)


def embed_sources(spec):
    _base_embed_sources(spec)
    try:
        text = bpy.data.texts.new("SOURCE_native_generate_vfx_v13.py")
        text.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError:
        pass


base.setup_scene = setup_scene
base.build_frame = build_frame
base.embed_sources = embed_sources

if __name__ == "__main__":
    base.main()
