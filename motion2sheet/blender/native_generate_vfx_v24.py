"""Blender-native VFX renderer V24: balanced F5->F6 dissolve progression."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import bpy

_V23_PATH=Path(__file__).with_name("native_generate_vfx_v23.py")
_SPEC=importlib.util.spec_from_file_location("motion2sheet_native_vfx_v23",_V23_PATH)
if _SPEC is None or _SPEC.loader is None: raise RuntimeError("Unable to load V23")
v23=importlib.util.module_from_spec(_SPEC); _SPEC.loader.exec_module(v23)
v22,v21,v20,v19,v18,v17,v16,v15,v14,v13,v12,v9,v8,v7,v6,base=(v23.v22,v23.v21,v23.v20,v23.v19,v23.v18,v23.v17,v23.v16,v23.v15,v23.v14,v23.v13,v23.v12,v23.v9,v23.v8,v23.v7,v23.v6,v23.base)

_ORIG_TRI_VIS=v23._ORIG_TRI_VIS


def setup_scene(spec):
    scene,layers=v23.setup_scene(spec)
    scene["vfx_renderer"]="blender-native-v24"
    scene["vfx_animation_balance"]="gentler-f6-before-late-breakup"
    return scene,layers


def tri_visibility(u,v,tier,p,seed,index,frames,tri):
    if index==frames-3:
        # F6 is the first dissolve frame. Evaluate the same coherent noise field
        # at a lower effective strength rather than artificially filling triangles.
        # This preserves real holes while keeping substantially more plasma mass.
        local=dict(p)
        local["dissolve.strength"]=float(p["dissolve.strength"])*.46
        return _ORIG_TRI_VIS(u,v,tier,local,seed,index,frames,tri)
    return _ORIG_TRI_VIS(u,v,tier,p,seed,index,frames,tri)


def embed_sources(spec):
    v23.embed_sources(spec)
    try:
        t=bpy.data.texts.new("SOURCE_native_generate_vfx_v24.py"); t.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError: pass

v9.tri_visibility=tri_visibility
base.setup_scene=setup_scene
base.make_materials=v14.make_materials
base.build_frame=v23.build_frame
base.embed_sources=embed_sources

if __name__=="__main__": base.main()
