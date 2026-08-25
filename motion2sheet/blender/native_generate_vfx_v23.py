"""Blender-native VFX renderer V23: coherent mild-hole F6 dissolve mesh."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import bpy

_V22_PATH=Path(__file__).with_name("native_generate_vfx_v22.py")
_SPEC=importlib.util.spec_from_file_location("motion2sheet_native_vfx_v22",_V22_PATH)
if _SPEC is None or _SPEC.loader is None: raise RuntimeError("Unable to load V22")
v22=importlib.util.module_from_spec(_SPEC); _SPEC.loader.exec_module(v22)
v21,v20,v19,v18,v17,v16,v15,v14,v13,v12,v9,v8,v7,v6,base=(v22.v21,v22.v20,v22.v19,v22.v18,v22.v17,v22.v16,v22.v15,v22.v14,v22.v13,v22.v12,v22.v9,v22.v8,v22.v7,v22.v6,v22.base)

_ORIG_TRI_VIS=v9.tri_visibility


def setup_scene(spec):
    scene,layers=v21.setup_scene(spec)
    scene["vfx_renderer"]="blender-native-v23"
    scene["vfx_f6_transition"]="mild-hole-eroded-mesh-with-live-core"
    return scene,layers


def tri_visibility(u,v,tier,p,seed,index,frames,tri):
    vis=_ORIG_TRI_VIS(u,v,tier,p,seed,index,frames,tri)
    if index==frames-3:
        # Keep most of the F6 surface, but preserve a few deterministic openings.
        boost=.38 if tier=="body" else .44 if tier=="inner" else .48
        return base.clamp01(vis+boost)
    return vis


def build_frame(spec,index,materials,layers):
    p=spec["params"]; v14._ACTIVE_PARAMS=p
    radius=float(p["radius"]); frames=int(spec["frames"]); seed=int(spec["seed"])
    tail,head,energy,breakup=v6.motion_window(index,frames,float(p["timing.peak"])); prefix=f"F{index+1:02d}"
    if index==0:
        v9.add_ignition(prefix,p,radius,materials,layers,seed,index,frames); return
    progress=base.dissolve_progress(p,index,frames,core=False); strength=float(p["dissolve.strength"])

    if progress<=0:
        if strength<=0 and index>=frames-2:
            v18.add_coherent_late_baseline(prefix,p,radius,tail,head,materials,layers,seed,index,frames); return
        v17.add_powered_mass(prefix,p,radius,tail,head,materials,layers,seed,index,frames)
        v19.add_directional_tongues(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
        v18.add_core(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
        v18.add_hotspots(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,breakup)
        v21.add_lightning(prefix,p,radius,tail,head,energy,breakup,materials,layers,seed,index,frames)
        return

    removed=[]
    removed+=v9.add_ribbon(prefix+"_erode_outer","body",p,radius,tail,head,materials["outer"],layers["BODY"],seed,index,frames,.08,2.55,.34,1.12)
    removed+=v9.add_ribbon(prefix+"_erode_body","body",p,radius,tail,head,materials["body"],layers["BODY"],seed+31,index,frames,.14,1.55,.22,1.0)
    removed+=v9.add_ribbon(prefix+"_erode_inner","inner",p,radius,tail,head,materials["inner"],layers["BODY"],seed+47,index,frames,.26,.18,.04,.62)

    if index==frames-3:
        # Core/lightning survive the first breakup frame; only shell starts opening.
        v18.add_core(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,min(breakup,.50))
        v18.add_hotspots(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,min(breakup,.50))
        v21.add_lightning(prefix,p,radius,tail,head,energy,min(breakup,.50),materials,layers,seed,index,frames)
        if removed:
            v8.add_fragments(prefix,removed[::6],p,materials,layers,radius,seed,index,frames,breakup)
        return

    v8.add_fragments(prefix,removed,p,materials,layers,radius,seed,index,frames,breakup)
    if index==frames-1:
        v13.add_terminal_shards(prefix,p,radius,tail,head,materials,layers,seed,index,frames)


def embed_sources(spec):
    v22.embed_sources(spec)
    try:
        t=bpy.data.texts.new("SOURCE_native_generate_vfx_v23.py"); t.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError: pass

v9.tri_visibility=tri_visibility
v17._band_polygon=v19._band_polygon
v12.point_on_spine=v16.point_on_spine; v9.point_on_spine=v16.point_on_spine; v8.point_on_spine=v16.point_on_spine; v7.point_on_spine=v16.point_on_spine; base.point_on_arc=v16.point_on_spine
base.setup_scene=setup_scene; base.make_materials=v14.make_materials; base.build_frame=build_frame; base.embed_sources=embed_sources
if __name__=="__main__": base.main()
