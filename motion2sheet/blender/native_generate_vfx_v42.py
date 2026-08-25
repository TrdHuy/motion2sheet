"""Blender-native VFX renderer V42: stronger in-alpha core energy aura."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import bpy

_V41_PATH = Path(__file__).with_name("native_generate_vfx_v41.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v41", _V41_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load V41")
v41 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v41)

v40, v14, base = v41.v40, v41.v14, v41.base


def setup_scene(spec):
    scene, layers = v41.setup_scene(spec)
    scene["vfx_renderer"] = "blender-native-v42"
    scene["vfx_core_aura_model"] = "stronger-semitransparent-cyan-white-energy-bed"
    return scene, layers


def make_materials(p):
    """Keep V41 colors but let the authored core aura survive RGBA export."""
    materials = v14.make_materials(p)
    inner = base.hex_rgba(str(p["colors.inner"]))
    core = base.hex_rgba(str(p["colors.core"]))

    # V34 compositor bloom was intentionally constrained by original alpha.
    # V42 instead strengthens actual Blender geometry/material alpha around the
    # V41 core, so exported transparent sprites retain the aura deterministically.
    materials["inner_glow"] = base.emission_material(
        "VFX_InnerGlow_V42", inner,
        1.05 + float(p["glow.inner_strength"]) * 1.35,
        .14,
    )
    materials["core_glow"] = base.emission_material(
        "VFX_CoreGlow_V42", core,
        1.45 + float(p["glow.core_strength"]) * 1.80,
        .10,
    )
    return materials


def embed_sources(spec):
    v41.embed_sources(spec)
    try:
        text = bpy.data.texts.new("SOURCE_native_generate_vfx_v42.py")
        text.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError:
        pass

base.setup_scene = setup_scene
base.make_materials = make_materials
base.embed_sources = embed_sources

if __name__ == "__main__":
    base.main()
