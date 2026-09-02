from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

PANEL = 256
COLUMNS = 8
PADDING = 18
EDGES = (("leftShoulder","rightShoulder"),("pelvis","head"),("leftShoulder","leftElbow"),("leftElbow","leftWrist"),("rightShoulder","rightElbow"),("rightElbow","rightWrist"),("pelvis","leftHip"),("leftHip","leftKnee"),("leftKnee","leftAnkle"),("pelvis","rightHip"),("rightHip","rightKnee"),("rightKnee","rightAnkle"))


def _bounds(frames):
    xs, zs = [], []
    for frame in frames:
        for point in frame["semantics"].values():
            xs.append(float(point[0])); zs.append(float(point[2]))
    if not xs or not zs:
        raise ValueError("retarget semantic render has no points")
    xmin,xmax,zmin,zmax=min(xs),max(xs),min(zs),max(zs)
    pad=0.08*max(max(1e-6,xmax-xmin),max(1e-6,zmax-zmin))
    return xmin-pad,xmax+pad,zmin-pad,zmax+pad


def _project(point,bounds):
    xmin,xmax,zmin,zmax=bounds
    scale=min((PANEL-2*PADDING)/max(1e-9,xmax-xmin),(PANEL-2*PADDING)/max(1e-9,zmax-zmin))
    used_w=(xmax-xmin)*scale; used_h=(zmax-zmin)*scale
    ox=(PANEL-used_w)*0.5; oy=(PANEL-used_h)*0.5
    return round(ox+(float(point[0])-xmin)*scale), round(PANEL-(oy+(float(point[2])-zmin)*scale))


def _panel(frame,bounds):
    image=Image.new("RGB",(PANEL,PANEL),(255,255,255)); draw=ImageDraw.Draw(image); points=frame["semantics"]
    for a,b in EDGES:
        if a not in points or b not in points: raise ValueError(f"retarget visual semantic missing: {a}/{b}")
        draw.line([_project(points[a],bounds),_project(points[b],bounds)],fill=(20,20,20),width=4)
    for name,p in points.items():
        if name=="root": continue
        x,y=_project(p,bounds); draw.ellipse((x-3,y-3,x+3,y+3),fill=(20,20,20))
    draw.text((8,8),f"F{frame['frame']}",fill=(20,20,20)); return image


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--conversion",required=True); parser.add_argument("--output",required=True); args=parser.parse_args()
    report=json.loads(Path(args.conversion).read_text(encoding="utf-8")); frames=report.get("targetPoseFrames")
    if not isinstance(frames,list) or not frames: raise ValueError("conversion report has no targetPoseFrames")
    if not report.get("retargetFidelity",{}).get("pass"): raise ValueError("refusing to render retarget skeleton for failed source->retarget gate")
    output=Path(args.output); output.mkdir(parents=True,exist_ok=True); bounds=_bounds(frames); panels=[_panel(frame,bounds) for frame in frames]
    rows=math.ceil(len(panels)/COLUMNS); sheet=Image.new("RGB",(COLUMNS*PANEL,rows*PANEL),(255,255,255))
    for index,panel in enumerate(panels): sheet.paste(panel,((index%COLUMNS)*PANEL,(index//COLUMNS)*PANEL))
    sheet.save(output/"pose_sheet.png"); fps=float(report["source"]["fps"]); duration=max(1,round(1000.0/fps))
    panels[0].save(output/"preview.gif",save_all=True,append_images=panels[1:],duration=duration,loop=0,disposal=2,optimize=False)
    metadata={"frameCount":len(frames),"fps":fps,"panel":[PANEL,PANEL],"columns":COLUMNS,"rows":rows,"sheet":[sheet.width,sheet.height],"projection":"target-world X/Z semantic skeleton","bounds":[round(v,9) for v in bounds]}
    (output/"render.json").write_text(json.dumps(metadata,indent=2)+"\n",encoding="utf-8")
    for panel in panels: panel.close()
    sheet.close(); print(json.dumps(metadata),flush=True); return 0


if __name__=="__main__": raise SystemExit(main())
