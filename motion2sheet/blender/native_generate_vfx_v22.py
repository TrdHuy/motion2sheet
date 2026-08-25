"""Blender-native VFX renderer V22: gradual F6 plasma breakup transition."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import bpy

_V21_PATH=Path(__file__).with_name("native_generate_vfx_v21.py")
_SPEC=importlib.util.spec_from_file_location("motion2sheet_native_vfx_v21",_V21_PATH)
if _SPEC is None or _SPEC.loader is None: raise RuntimeError("Unable to load V21")
v21=importlib.util.module_from_spec(_SPEC); _SPEC.loader.exec_module(v21)
v20,v19,v18,v17,v16,v15,v14,v13,v12,v9,v8,v7,v6,base=v21.v20,v21.v19,v21.v18,v21.v17,v21.v16,v21.v15,v21.v14,v21.v13,v21.v12,v21.v9,v21.v8,v21.v7,v21.v6,v21.base


def setup_scene(spec):
    scene,layers=v21.setup_scene(spec)
    scene["vfx_renderer"]="blender-native-v22"
    scene["vfx_f6_transition"]="segmented-coherent-plasma-with-small-cut-gaps"
    return scene,layers


def add_f6_transition(prefix,p,radius,tail,head,materials,layers,seed,index,frames,energy,breakup):
    """Keep F6 visually close to peak while introducing the first real gaps."""
    # Three narrow gaps across the arc: enough to read as the onset of breakup,
    # but much less destructive than switching straight to the late eroded mesh.
    intervals=((0.00,.205),(.220,.455),(.470,.700),(.716,1.00))
    specs=(
        ("haze",2.90,.46,materials["outer_glow"],layers["PLASMA"],.03,0),
        ("outer",2.42,.33,materials["outer"],layers["BODY"],.08,17),
        ("body",1.48,.21,materials["body"],layers["BODY"],.14,31),
        ("inner",.70,.095,materials["inner"],layers["BODY"],.25,47),
    )
    for seg,(qa,qb) in enumerate(intervals):
        ta=tail+(head-tail)*qa; hb=tail+(head-tail)*qb
        for name,os,is_,mat,coll,z,off in specs:
            poly=v19._band_polygon(p,radius,ta,hb,os,is_,seed+off+seg*1009,off*.013+seg*.17)
            base.add_polygon(f"{prefix}_f6_{seg}_{name}",poly,mat,coll,z=z,frame=index+1,frames=frames)
    # Preserve the hot core and lightning during the first breakup frame so F6
    # still feels energetic rather than instantly collapsing into cold shards.
    v18.add_core(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,min(breakup,.48))
    v18.add_hotspots(prefix,p,radius,tail,head,energy,materials,layers,seed,index,frames,min(breakup,.48))
    v21.add_lightning(prefix,p,radius,tail,head,energy,min(breakup,.48),materials,layers,seed,index,frames)


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
    if index==frames-3:
        add_f6_transition(prefix,p,radius,tail,head,materials,layers,seed,index,frames,energy,breakup)
        return
    removed=[]
    removed+=v9.add_ribbon(prefix+"_erode_outer","body",p,radius,tail,head,materials["outer"],layers["BODY"],seed,index,frames,.08,2.55,.34,1.12)
    removed+=v9.add_ribbon(prefix+"_erode_body","body",p,radius,tail,head,materials["body"],layers["BODY"],seed+31,index,frames,.14,1.55,.22,1.0)
    removed+=v9.add_ribbon(prefix+"_erode_inner","inner",p,radius,tail,head,materials["inner"],layers["BODY"],seed+47,index,frames,.26,.18,.04,.62)
    v8.add_fragments(prefix,removed,p,materials,layers,radius,seed,index,frames,breakup)
    if index==frames-1:
        v13.add_terminal_shards(prefix,p,radius,tail,head,materials,layers,seed,index,frames)


def embed_sources(spec):
    v21.embed_sources(spec)
    try:
        t=bpy.data.texts.new("SOURCE_native_generate_vfx_v22.py"); t.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError: pass

v17._band_polygon=v19._band_polygon
v12.point_on_spine=v16.point_on_spine; v9.point_on_spine=v16.point_on_spine; v8.point_on_spine=v16.point_on_spine; v7.point_on_spine=v16.point_on_spine; base.point_on_arc=v16.point_on_spine
base.setup_scene=setup_scene; base.make_materials=v14.make_materials; base.build_frame=build_frame; base.embed_sources=embed_sources
if __name__=="__main__": base.main()
