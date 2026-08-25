"""Blender-native VFX renderer V38: reframe the slash so hot geometry is not clipped."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import bpy

_V37_PATH = Path(__file__).with_name("native_generate_vfx_v37.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v37", _V37_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load V37")
v37 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v37)

base = v37.base


def setup_scene(spec):
    scene, layers = v37.setup_scene(spec)
    cam = scene.camera
    # V37 finally places F1 at the true upper F2 endpoint, which exposed a
    # framing problem: F1-F5 touched/clipped the top/right render borders.
    # Keep all geometry identical and give the authored VFX breathing room.
    cam.data.ortho_scale *= 1.10
    cam.location.x += 0.28
    cam.location.y += 0.28
    scene["vfx_renderer"] = "blender-native-v38"
    scene["vfx_framing_model"] = "ten-percent-wider-camera-with-top-right-breathing-room"
    return scene, layers


def embed_sources(spec):
    v37.embed_sources(spec)
    try:
        text = bpy.data.texts.new("SOURCE_native_generate_vfx_v38.py")
        text.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError:
        pass

base.setup_scene = setup_scene
base.embed_sources = embed_sources

if __name__ == "__main__":
    base.main()
