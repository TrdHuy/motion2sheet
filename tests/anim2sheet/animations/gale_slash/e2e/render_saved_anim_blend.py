from __future__ import annotations
import argparse, sys
from pathlib import Path
import bpy

argv=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
p=argparse.ArgumentParser(); p.add_argument("--output",required=True); args=p.parse_args(argv)
out=Path(args.output); out.mkdir(parents=True,exist_ok=True)
scene=bpy.context.scene
for frame in range(scene.frame_start,scene.frame_end+1):
    scene.frame_set(frame); scene.render.filepath=str((out/f"{frame:02d}.png").resolve()); bpy.ops.render.render(write_still=True)
