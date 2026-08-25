"""Blender-native VFX renderer V26: sparse deep-hole first dissolve frame."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import bpy

_V25_PATH=Path(__file__).with_name("native_generate_vfx_v25.py")
_SPEC=importlib.util.spec_from_file_location("motion2sheet_native_vfx_v25",_V25_PATH)
if _SPEC is None or _SPEC.loader is None: raise RuntimeError("Unable to load V25")
v25=importlib.util.module_from_spec(_SPEC); _SPEC.loader.exec_module(v25)
v24,v23=v25.v24,v25.v23
v22,v21,v20,v19,v18,v17,v16,v15,v14,v13,v12,v9,v8,v7,v6,base=(v23.v22,v23.v21,v23.v20,v23.v19,v23.v18,v23.v17,v23.v16,v23.v15,v23.v14,v23.v13,v23.v12,v23.v9,v23.v8,v23.v7,v23.v6,v23.base)
_ORIG_TRI_VIS=v23._ORIG_TRI_VIS


def setup_scene(spec):
    scene,layers=v23.setup_scene(spec)
    scene["vfx_renderer"]="blender-native-v26"
    scene["vfx_f6_transition"]="sparse-deep-coherent-holes"
    return scene,layers


def tri_visibility(u,v,tier,p,seed,index,frames,tri):
    vis=_ORIG_TRI_VIS(u,v,tier,p,seed,index,frames,tri)
    if index==frames-3:
        # V9's dissolve turns on eight coherent hole fields as soon as progress is
        # non-zero. For the first breakup frame retain only the deepest centers of
        # those same fields. This gives a few true openings without prematurely
        # destroying almost half the plasma body.
        cutoff=.16 if tier=="body" else .12 if tier=="inner" else .10
        return 0.0 if vis < cutoff else 1.0
    return vis


def embed_sources(spec):
    v25.embed_sources(spec)
    try:
        t=bpy.data.texts.new("SOURCE_native_generate_vfx_v26.py"); t.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError: pass

v9.tri_visibility=tri_visibility
base.setup_scene=setup_scene
base.make_materials=v14.make_materials
base.build_frame=v23.build_frame
base.embed_sources=embed_sources
if __name__=="__main__": base.main()
