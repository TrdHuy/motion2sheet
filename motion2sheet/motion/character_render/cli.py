from __future__ import annotations
import argparse
from pathlib import Path
from .runner import render_character_animation

def _canvas(value: str) -> tuple[int,int]:
    try: a,b=value.lower().split('x',1); result=(int(a),int(b))
    except Exception as exc: raise argparse.ArgumentTypeError("canvas must look like 320x320") from exc
    if result[0]<=0 or result[1]<=0: raise argparse.ArgumentTypeError("canvas dimensions must be positive")
    return result

def _run(args) -> int:
    report=render_character_animation(rig_path=Path(args.rig),animation_path=Path(args.animation),character_profile_path=Path(args.character_profile),camera_profile_path=Path(args.camera_profile),output=Path(args.output),sheet_columns=args.sheet_columns,canvas=args.canvas,background=args.background,gif=args.gif,frames=args.frames,blender=args.blender)
    print(f"motion2sheet: character render OK; frames={report['frameCount']} bones={report['rigCompatibility']['boneCount']} -> {args.output}")
    return 0

def add_character_render_subcommands(subparsers) -> None:
    p=subparsers.add_parser("render-character-animation",help="Render Contract B source animation on a strictly compatible character rig")
    p.add_argument("--rig",required=True); p.add_argument("--animation",required=True); p.add_argument("--character-profile",required=True); p.add_argument("--camera-profile",required=True); p.add_argument("--sheet-columns",type=int,default=8); p.add_argument("--canvas",type=_canvas,default=(320,320)); p.add_argument("--background",default="transparent"); p.add_argument("--gif",action="store_true"); p.add_argument("--frames",default="all"); p.add_argument("--blender",default="blender"); p.add_argument("--output",required=True); p.set_defaults(func=_run)
