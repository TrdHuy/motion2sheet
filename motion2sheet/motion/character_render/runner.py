from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image
from motion2sheet.motion.roundtrip.schema import read_json, validate_animation_document, validate_rig_document

from .profile import load_camera_profile, load_character_profile, validate_character_compatibility

GIF_TIME_QUANTUM_MS = 10


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(data,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")

def parse_frames(value: str, animation: dict[str, Any]) -> list[int]:
    available=[int(row["frame"]) for row in animation["frames"]]; aset=set(available)
    if value.strip().lower() in {"all","*"}: return available
    out=[]
    for token in value.split(','):
        token=token.strip()
        if not token: continue
        if '-' in token:
            a,b=token.split('-',1); start,end=int(a),int(b); step=1 if end>=start else -1; out.extend(range(start,end+step,step))
        else: out.append(int(token))
    if not out: raise ValueError("--frames selected no frames")
    if len(set(out))!=len(out): raise ValueError("--frames contains duplicate frames")
    missing=[f for f in out if f not in aset]
    if missing: raise ValueError(f"--frames contains frames outside Contract B: {missing}")
    return out

def _background(value: str) -> dict[str, Any]:
    if value=="transparent": return {"transparent":True,"rgba":[0.0,0.0,0.0,0.0]}
    if len(value)==7 and value.startswith('#'):
        try: rgb=[int(value[i:i+2],16)/255.0 for i in (1,3,5)]
        except ValueError as exc: raise ValueError("background must be transparent or #RRGGBB") from exc
        return {"transparent":False,"rgba":[*rgb,1.0]}
    raise ValueError("background must be transparent or #RRGGBB")

def _compose_sheet(frame_paths: list[Path], output: Path, columns: int, canvas: tuple[int,int]) -> tuple[int,int,int]:
    rows=(len(frame_paths)+columns-1)//columns; sheet=Image.new("RGBA",(columns*canvas[0],rows*canvas[1]),(0,0,0,0))
    for i,path in enumerate(frame_paths):
        with Image.open(path) as im: sheet.alpha_composite(im.convert("RGBA"),(i%columns*canvas[0],i//columns*canvas[1]))
    sheet.save(output); size=sheet.size; sheet.close(); return rows,size[0],size[1]

def gif_frame_durations_ms(frame_count: int, fps: float) -> list[int]:
    if frame_count <= 0: raise ValueError("GIF frame count must be positive")
    if not math.isfinite(fps) or fps <= 0: raise ValueError("GIF FPS must be positive and finite")
    # GIF stores frame delays in 10 ms centiseconds. Quantize cumulative source-time
    # boundaries instead of each frame independently so rounding error is distributed.
    boundaries=[]
    for index in range(frame_count+1):
        ideal_ms=index*1000.0/fps
        quantized=int(math.floor(ideal_ms/GIF_TIME_QUANTUM_MS+0.5))*GIF_TIME_QUANTUM_MS
        boundaries.append(quantized)
    durations=[boundaries[index+1]-boundaries[index] for index in range(frame_count)]
    if any(duration < GIF_TIME_QUANTUM_MS for duration in durations):
        raise ValueError(f"GIF timing cannot represent {fps:g} FPS without zero-duration frames")
    return durations

def _compose_gif(frame_paths: list[Path], output: Path, fps: float) -> dict[str, Any]:
    durations=gif_frame_durations_ms(len(frame_paths),fps); images=[Image.open(p).convert("RGBA") for p in frame_paths]
    try: images[0].save(output,save_all=True,append_images=images[1:],duration=durations,loop=0,disposal=2,optimize=False)
    finally:
        for im in images: im.close()
    total=sum(durations)
    return {"frameDurationsMs":durations,"totalDurationMs":total,"effectiveFps":len(durations)*1000.0/total,"quantumMs":GIF_TIME_QUANTUM_MS}

def render_character_animation(*, rig_path: Path, animation_path: Path, character_profile_path: Path, camera_profile_path: Path, output: Path, sheet_columns: int=8, canvas: tuple[int,int]=(320,320), background: str="transparent", gif: bool=False, frames: str="all", blender: str="blender") -> dict[str, Any]:
    rig=read_json(rig_path); animation=read_json(animation_path); validate_rig_document(rig); validate_animation_document(animation,rig)
    character=load_character_profile(character_profile_path); camera=load_camera_profile(camera_profile_path); compatibility=validate_character_compatibility(rig,character)
    selected=parse_frames(frames,animation)
    if sheet_columns<=0: raise ValueError("sheet columns must be positive")
    if canvas[0]<=0 or canvas[1]<=0: raise ValueError("canvas dimensions must be positive")
    executable=shutil.which(blender) if Path(blender).name==blender else blender
    if not executable: raise RuntimeError(f"Blender executable not found: {blender}")
    output=output.resolve(); output.mkdir(parents=True,exist_ok=True); frame_dir=output/".frames"; shutil.rmtree(frame_dir,ignore_errors=True); frame_dir.mkdir()
    request={"rigPath":str(rig_path.resolve()),"animationPath":str(animation_path.resolve()),"character":character,"camera":camera,"compatibility":compatibility,"selectedFrames":selected,"canvas":list(canvas),"background":_background(background),"output":str(output)}
    request_path=output/"diagnostics"/"render_request.json"; _write_json(request_path,request)
    script=Path(__file__).with_name("blender_entry.py")
    subprocess.run([str(executable),"--background","--factory-startup","--python-exit-code","1","--python",str(script),"--","--request",str(request_path)],check=True)
    frame_paths=[frame_dir/f"frame_{frame:04d}.png" for frame in selected]
    missing=[str(p) for p in frame_paths if not p.is_file()]
    if missing: raise RuntimeError(f"Blender character render missing frames: {missing[:4]}")
    rows,width,height=_compose_sheet(frame_paths,output/"pose_sheet.png",sheet_columns,canvas)
    gif_timing=_compose_gif(frame_paths,output/"preview.gif",float(animation["fps"])) if gif else None
    playback=json.loads((output/"diagnostics"/"playback.json").read_text(encoding="utf-8"))
    report={"schema":"motion2sheet.character-render","version":1,"sourceRig":{"id":rig["id"],"schema":rig["schema"],"boneCount":len(rig["bones"])},"sourceAnimation":{"id":animation["id"],"schema":animation["schema"],"frameCount":animation["frameCount"],"fps":animation["fps"]},"characterProfile":{"id":character["id"],"path":str(character_profile_path)},"cameraProfile":{"id":camera["id"],"path":str(camera_profile_path)},"renderedFrames":selected,"frameCount":len(selected),"fps":animation["fps"],"rigCompatibility":compatibility,"playbackFidelity":playback,"sourceMotionFileRequired":False,"layout":{"cellSize":list(canvas),"sheetColumns":sheet_columns,"sheetRows":rows,"sheetSize":[width,height]},"gifTiming":gif_timing,"outputs":{"poseSheet":"pose_sheet.png","previewGif":"preview.gif" if gif else None,"sourceBlend":"source.blend","diagnostics":"diagnostics/playback.json"}}
    _write_json(output/"render.json",report); shutil.rmtree(frame_dir,ignore_errors=True)
    return report
