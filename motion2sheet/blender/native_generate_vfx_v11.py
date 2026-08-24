"""Blender-native VFX renderer V11: coherent powered tail, fragmented dissolve tail."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_V10_PATH = Path(__file__).with_name("native_generate_vfx_v10.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v10", _V10_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load Blender-native V10 renderer")
v10 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v10)
v9, v8, v7, v6, base = v10.v9, v10.v9.v8, v10.v9.v7, v10.v9.v6, v10.base


def setup_scene(spec):
    scene, layers = v10.setup_scene(spec)
    scene["vfx_renderer"] = "blender-native-v11"
    scene["vfx_tail_coherence"] = "opaque-underlay-fragmented-by-shared-dissolve"
    return scene, layers


def build_frame(spec, index, materials, layers):
    p = spec["params"]
    radius = float(p["radius"])
    frames = int(spec["frames"])
    seed = int(spec["seed"])
    tail, head, energy, breakup = v6.motion_window(index, frames, float(p["timing.peak"]))
    prefix = f"F{index + 1:02d}"
    if index == 0:
        v9.add_ignition(prefix, p, radius, materials, layers, seed, index, frames)
        return

    # The dissolve-off reference should be one coherent powered plasma mass.
    # A slightly wider opaque deep-blue underlay absorbs threshold-level edge
    # islands from semi-transparent decorative layers. With dissolve enabled,
    # the exact same underlay is cut by the shared triangle field, so the final
    # tail genuinely gains disconnected components instead of merely losing them.
    removed = []
    if index >= frames - 2:
        removed += v9.add_ribbon(
            prefix + "_coherent_underlay", "body", p, radius, tail, head,
            materials["outer"], layers["BODY"], seed + 113, index, frames,
            0.045, 3.55, 0.74, 0.74,
        )

    removed += v9.add_ribbon(prefix + "_outer_haze", "body", p, radius, tail, head,
                             materials["outer_glow"], layers["PLASMA"], seed, index, frames,
                             .02, 3.15, .62, 1.05)
    removed += v9.add_ribbon(prefix + "_outer", "body", p, radius, tail, head,
                             materials["outer"], layers["BODY"], seed, index, frames,
                             .08, 2.62, .46, 1.0)
    removed += v9.add_ribbon(prefix + "_body", "body", p, radius, tail, head,
                             materials["body"], layers["BODY"], seed + 31, index, frames,
                             .14, 1.60, .28, .88)
    removed += v9.add_ribbon(prefix + "_inner", "inner", p, radius, tail, head,
                             materials["inner"], layers["BODY"], seed + 47, index, frames,
                             .28, .18, .055, .48)
    v9.add_flow_bundle(prefix, p, radius, tail, head, energy, materials, layers,
                       seed, index, frames, breakup)
    v8.add_hot_core(prefix, p, radius, tail, head, energy, materials, layers,
                    seed, index, frames, breakup)
    v10.add_lightning(prefix, p, radius, tail, head, energy, breakup, materials,
                      layers, seed, index, frames)
    v8.add_fragments(prefix, removed, p, materials, layers, radius, seed, index,
                     frames, breakup)


base.setup_scene = setup_scene
base.build_frame = build_frame
base.embed_sources = v9.embed_sources

if __name__ == "__main__":
    base.main()
