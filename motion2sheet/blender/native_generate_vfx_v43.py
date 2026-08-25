"""Blender-native VFX renderer V43: pronounced RGBA-visible white/cyan core aura."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import bpy

_V42_PATH = Path(__file__).with_name("native_generate_vfx_v42.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v42", _V42_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load V42")
v42 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v42)

v41, v14, base = v42.v41, v42.v14, v42.base


def setup_scene(spec):
    scene, layers = v42.setup_scene(spec)
    scene["vfx_renderer"] = "blender-native-v43"
    scene["vfx_core_aura_model"] = "pronounced-rgba-cyan-white-aura"
    return scene, layers


def make_materials(p):
    materials = v14.make_materials(p)
    inner = base.hex_rgba(str(p["colors.inner"]))
    core = base.hex_rgba(str(p["colors.core"]))

    # Strong enough to be visually obvious in the exported transparent PNG,
    # but still geometry-backed and fully Blender-native/deterministic.
    materials["inner_glow"] = base.emission_material(
        "VFX_InnerGlow_V43", inner,
        1.38 + float(p["glow.inner_strength"]) * 1.65,
        .24,
    )
    materials["core_glow"] = base.emission_material(
        "VFX_CoreGlow_V43", core,
        2.00 + float(p["glow.core_strength"]) * 2.15,
        .18,
    )
    return materials


def embed_sources(spec):
    v42.embed_sources(spec)
    try:
        text = bpy.data.texts.new("SOURCE_native_generate_vfx_v43.py")
        text.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError:
        pass

base.setup_scene = setup_scene
base.make_materials = make_materials
base.embed_sources = embed_sources

if __name__ == "__main__":
    base.main()
