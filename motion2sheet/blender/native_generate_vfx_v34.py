"""Blender-native VFX renderer V34: compositor fog-glow polish on segmented core."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import bpy

_V33_PATH = Path(__file__).with_name("native_generate_vfx_v33.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v33", _V33_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load V33")
v33 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v33)

v32, v31, v30, v29, v28, v27, v23 = v33.v32, v33.v31, v33.v30, v33.v29, v33.v28, v33.v27, v33.v23
v21, v19, v18, v17, v16, v14 = v33.v21, v33.v19, v33.v18, v33.v17, v33.v16, v33.v14
v12, v9, v8, v7, v6, base = v33.v12, v33.v9, v33.v8, v33.v7, v33.v6, v33.base


def _setup_fog_glow(scene):
    """Add deterministic Blender compositor bloom while preserving source alpha."""
    scene.use_nodes = True
    tree = scene.node_tree
    nodes = tree.nodes
    links = tree.links
    nodes.clear()

    render = nodes.new("CompositorNodeRLayers")
    render.name = "VFX_RenderLayers"

    glare = nodes.new("CompositorNodeGlare")
    glare.name = "VFX_ElectricFogGlow"
    glare.glare_type = "FOG_GLOW"
    glare.quality = "HIGH"
    glare.threshold = 0.72
    glare.size = 7
    glare.mix = -0.12

    set_alpha = nodes.new("CompositorNodeSetAlpha")
    set_alpha.name = "VFX_PreserveTransparentAlpha"

    composite = nodes.new("CompositorNodeComposite")
    composite.name = "VFX_FinalComposite"

    links.new(render.outputs["Image"], glare.inputs["Image"])
    links.new(glare.outputs["Image"], set_alpha.inputs["Image"])
    links.new(render.outputs["Alpha"], set_alpha.inputs["Alpha"])
    links.new(set_alpha.outputs["Image"], composite.inputs["Image"])


def setup_scene(spec):
    scene, layers = v33.setup_scene(spec)
    _setup_fog_glow(scene)
    scene["vfx_renderer"] = "blender-native-v34"
    scene["vfx_glow_model"] = "blender-compositor-fog-glow-alpha-preserved"
    scene["vfx_glow_threshold"] = 0.72
    scene["vfx_glow_size"] = 7
    scene["vfx_glow_mix"] = -0.12
    return scene, layers


def embed_sources(spec):
    v33.embed_sources(spec)
    try:
        text = bpy.data.texts.new("SOURCE_native_generate_vfx_v34.py")
        text.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError:
        pass

v29.tri_visibility = v32.tri_visibility
v9.tri_visibility = v32.tri_visibility
v9.add_ribbon = v29.add_ribbon
v8.add_fragments = v29.add_fragments
v9.add_ignition = v30.add_ignition
v21.add_lightning = v28.add_lightning
v6.motion_window = v27.motion_window
v18.add_core = v33.add_core
v17._band_polygon = v19._band_polygon
v12.point_on_spine = v16.point_on_spine; v9.point_on_spine = v16.point_on_spine; v8.point_on_spine = v16.point_on_spine; v7.point_on_spine = v16.point_on_spine; base.point_on_arc = v16.point_on_spine
base.setup_scene = setup_scene; base.make_materials = v14.make_materials; base.build_frame = v23.build_frame; base.embed_sources = embed_sources

if __name__ == "__main__":
    base.main()
