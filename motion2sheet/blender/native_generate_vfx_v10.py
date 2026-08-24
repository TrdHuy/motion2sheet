"""Blender-native VFX renderer V10: V9 morphology with coherent late baseline."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_V9_PATH = Path(__file__).with_name("native_generate_vfx_v9.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v9", _V9_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load Blender-native V9 renderer")
v9 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v9)

base = v9.base
_original_lightning = v9.v7.add_lightning


def add_lightning(prefix, p, radius, tail, head, energy, breakup, materials, layers, seed, index, frames):
    # By late breakup the plasma itself carries the curved motion memory.
    # Do not seed the dissolve-off baseline with dozens of disconnected
    # lightning micro-islands; late fragmentation must come from dissolve.
    if breakup > 0.72:
        return
    return _original_lightning(prefix, p, radius, tail, head, energy, breakup,
                               materials, layers, seed, index, frames)


def setup_scene(spec):
    scene, layers = v9.setup_scene(spec)
    scene["vfx_renderer"] = "blender-native-v10"
    scene["vfx_late_lightning"] = "suppressed-after-72pct-breakup"
    return scene, layers


v9.v7.add_lightning = add_lightning
base.setup_scene = setup_scene
base.build_frame = v9.build_frame
base.embed_sources = v9.embed_sources

if __name__ == "__main__":
    base.main()
