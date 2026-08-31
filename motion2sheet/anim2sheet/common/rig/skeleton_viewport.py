"""Render the actual Blender armature for animation and rig inspection."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import bpy
from mathutils import Vector
from motion2sheet.anim2sheet.common.camera.blender import apply_camera_config

SWORD_OBJECTS = {"SwordGrip", "SwordBlade"}


def argv(): return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def parse_args():
    p=argparse.ArgumentParser(add_help=False); p.add_argument("--output",required=True); p.add_argument("--rig-output",required=True); p.add_argument("--frames",default=None); p.add_argument("--skip-rig-docs",action="store_true"); p.add_argument("--camera-config",default=None); p.add_argument("--camera-name",default=None); return p.parse_args(argv())
def find_view3d_context():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type=="VIEW_3D":
                region=next((v for v in area.regions if v.type=="WINDOW"),None)
                if region is not None: return window,area,region,area.spaces.active
    raise RuntimeError("No VIEW_3D area available for Blender viewport rendering")
def find_armature():
    values=[obj for obj in bpy.context.scene.objects if obj.type=="ARMATURE"]
    if len(values)!=1: raise RuntimeError(f"Expected exactly one armature, found {len(values)}")
    return values[0]
def prepare_armature(arm):
    for obj in bpy.context.scene.objects:
        if obj.type=="MESH" and obj.name not in SWORD_OBJECTS: obj.hide_set(True)
    bpy.ops.object.select_all(action="DESELECT"); arm.hide_set(False); arm.select_set(True); bpy.context.view_layer.objects.active=arm; arm.show_in_front=True; arm.data.display_type="BBONE"
def configure_camera(scene,args):
    if args.camera_config and args.camera_name:
        config=json.loads(Path(args.camera_config).read_text(encoding="utf-8")); apply_camera_config(scene,config["cameras"][args.camera_name])
def render_frame(scene,arm,path):
    window,area,region,space=find_view3d_context(); space.region_3d.view_perspective="CAMERA"; scene.camera.data.show_passepartout=False
    with bpy.context.temp_override(window=window,area=area,region=region):
        bpy.ops.screen.screenshot_area(filepath=str(path))
def write_rig_docs(arm,root):
    bones=[]
    for bone in arm.data.bones:
        bones.append({"name":bone.name,"parent":bone.parent.name if bone.parent else None,"connected":bool(bone.use_connect),"deform":bool(bone.use_deform),"length":round(float(bone.length),6)})
    payload={"armature":arm.name,"boneCount":len(bones),"bones":bones}; (root/"rig_bones.json").write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8")
    (root/"rig_bones.txt").write_text("\n".join(f"{b['name']} <- {b['parent'] or '-'}" for b in bones)+"\n",encoding="utf-8")
def main():
    args=parse_args(); output=Path(args.output).resolve(); rig_output=Path(args.rig_output).resolve(); output.mkdir(parents=True,exist_ok=True); rig_output.mkdir(parents=True,exist_ok=True); scene=bpy.context.scene; arm=find_armature(); prepare_armature(arm); configure_camera(scene,args)
    frames=[int(v.strip()) for v in args.frames.split(",") if v.strip()] if args.frames else list(range(scene.frame_start,scene.frame_end+1))
    for frame in frames:
        scene.frame_set(frame); bpy.context.view_layer.update(); render_frame(scene,arm,output/f"{frame:02d}.png")
    if not args.skip_rig_docs:
        write_rig_docs(arm,rig_output)
    print(f"anim2sheet skeleton viewport OK: {frames}",flush=True); return 0
if __name__=="__main__": raise SystemExit(main())
