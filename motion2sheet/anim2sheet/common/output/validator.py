from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

REQUIRED_JSON = ("source.json", "metadata.json", "invocation.json", "resolved_config.json", "motion_debug.json", "camera_debug.json", "leg_ik_debug.json", "reopen_debug.json")
REQUIRED_FILES = (*REQUIRED_JSON, "source.blend")


def _read_json(path: Path, errors: list[str]) -> dict:
    try: value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path.name} is invalid: {exc}"); return {}
    if not isinstance(value, dict): errors.append(f"{path.name} must contain a JSON object"); return {}
    return value

def _frames(values) -> list[int]: return [int(value) for value in values]
def _validate_preview(path: Path, expected_frames: int, fps: float, errors: list[str], label: str) -> None:
    if not path.is_file(): errors.append(f"{label} preview.gif is missing"); return
    try: image=Image.open(path)
    except OSError as exc: errors.append(f"{label} preview.gif is invalid: {exc}"); return
    try:
        if int(getattr(image,"n_frames",1)) != expected_frames: errors.append(f"{label} preview.gif frame count must be {expected_frames}, got {getattr(image,'n_frames',1)}")
        expected_duration=1000.0/fps
        for index in range(int(getattr(image,"n_frames",1))):
            image.seek(index); duration=image.info.get("duration")
            if not isinstance(duration,(int,float)) or duration <= 0: errors.append(f"{label} preview.gif frame {index} has invalid duration"); continue
            if abs(float(duration)-expected_duration)>10.0: errors.append(f"{label} preview.gif frame {index} duration {duration}ms does not match fps {fps}")
    finally: image.close()

def validate_output(root: Path) -> list[str]:
    errors=[]; missing=[name for name in REQUIRED_FILES if not (root/name).exists()]
    if missing: return [f"{name} is missing" for name in missing]
    data={name:_read_json(root/name,errors) for name in REQUIRED_JSON}
    if errors: return errors
    source=data["source.json"]; metadata=data["metadata.json"]; invocation=data["invocation.json"]; resolved=data["resolved_config.json"]; motion=data["motion_debug.json"]; camera=data["camera_debug.json"]; leg=data["leg_ik_debug.json"]; reopen=data["reopen_debug.json"]
    if metadata.get("tool")!="anim2sheet": errors.append("metadata tool must be anim2sheet")
    if invocation.get("tool")!="anim2sheet": errors.append("invocation tool must be anim2sheet")
    if invocation.get("command") not in {"build","review"}: errors.append("invocation command must be build or review")
    if metadata.get("animation") != invocation.get("animation"): errors.append("metadata animation does not match invocation")
    if resolved.get("animation") != invocation.get("animation"): errors.append("resolved animation does not match invocation")
    id_map={"animationId":"animationProfileId","motionId":"motionProfileId","rigId":"rigProfileId","characterId":"characterProfileId","cameraId":"cameraProfileId"}
    for key,source_key in id_map.items():
        value=invocation.get(key)
        if not isinstance(value,str) or not value: errors.append(f"invocation {key} must be non-empty")
        if resolved.get(key)!=value: errors.append(f"resolved_config {key} does not match invocation")
        if metadata.get(key)!=value: errors.append(f"metadata {key} does not match invocation")
        if source.get(source_key)!=value: errors.append(f"source {source_key} does not match invocation {key}")
    if source.get("generator")!="profile-contract-v2": errors.append("source generator must be profile-contract-v2")
    if source.get("motionProfileData",{}).get("schema")!="anim2sheet.motion": errors.append("source motionProfileData must be Motion v2")
    try: motion_frames=_frames(invocation.get("motionFrames",[])); execution_frames=_frames(invocation.get("executionFrames",[]))
    except (TypeError,ValueError): return errors+["invocation frame lists must contain integers"]
    if not motion_frames: errors.append("invocation motionFrames is empty")
    if not execution_frames: errors.append("invocation executionFrames is empty")
    if any(frame not in motion_frames for frame in execution_frames): errors.append("executionFrames must be a subset of motionFrames")
    frame_sources={"metadata":metadata.get("reviewFrames",[]),"resolved_config":resolved.get("executionFrames",[]),"camera_debug":camera.get("reviewFrames",[]),"leg_ik_debug":leg.get("frames",[]),"reopen_debug":reopen.get("frames",[]),"motion_debug":[row.get("frame") for row in motion.get("samples",[])]}
    for label,values in frame_sources.items():
        try: actual=_frames(values)
        except (TypeError,ValueError): errors.append(f"{label} frame list is invalid"); continue
        if actual != execution_frames: errors.append(f"{label} frames do not match invocation executionFrames")
    if _frames(resolved.get("motionFrames",[])) != motion_frames: errors.append("resolved_config motionFrames do not match invocation")
    cameras=list(invocation.get("cameras",[]))
    if not cameras: errors.append("invocation cameras is empty")
    if list(metadata.get("reviewCameras",[])) != cameras: errors.append("metadata cameras do not match invocation")
    if list(resolved.get("cameras",[])) != cameras: errors.append("resolved_config cameras do not match invocation")
    if list(camera.get("selectedCameras",[])) != cameras: errors.append("camera_debug cameras do not match invocation")
    for camera_name in cameras:
        camera_root=root/"cameras"/camera_name
        for frame in execution_frames:
            for folder in ("frames","skeleton_frames","overlay_frames"):
                if not (camera_root/folder/f"{frame:02d}.png").is_file(): errors.append(f"missing {camera_name}/{folder}/F{frame}")
        for name in ("object_keyposes.png","skeleton_keyposes.png","object_skeleton_overlay.png"):
            if not (camera_root/name).is_file(): errors.append(f"missing {camera_name}/{name}")
    for name in ("object_keyposes.png","skeleton_keyposes.png","object_skeleton_overlay.png"):
        if not (root/name).is_file(): errors.append(f"{name} is missing")
    gif_enabled=invocation.get("gif",False)
    if not isinstance(gif_enabled,bool): errors.append("invocation gif must be boolean"); gif_enabled=False
    if resolved.get("gif",False) != gif_enabled: errors.append("resolved_config gif does not match invocation")
    if metadata.get("gifEnabled",False) != gif_enabled: errors.append("metadata gifEnabled does not match invocation")
    preview_paths=[root/"preview.gif",*[root/"cameras"/name/"preview.gif" for name in cameras]]
    if gif_enabled:
        fps=resolved.get("motionProfile",{}).get("fps")
        if isinstance(fps,bool) or not isinstance(fps,(int,float)) or fps<=0: errors.append("resolved motion profile fps must be positive when GIF preview is enabled")
        else:
            for camera_name in cameras: _validate_preview(root/"cameras"/camera_name/"preview.gif",len(execution_frames),float(fps),errors,camera_name)
            _validate_preview(root/"preview.gif",len(execution_frames),float(fps),errors,"top-level")
        alias_camera=metadata.get("aliasCamera")
        if alias_camera in cameras:
            alias_preview=root/"cameras"/str(alias_camera)/"preview.gif"; top_preview=root/"preview.gif"
            if alias_preview.is_file() and top_preview.is_file() and alias_preview.read_bytes()!=top_preview.read_bytes(): errors.append("top-level preview.gif must alias the selected final/alias camera GIF")
    else:
        for path in preview_paths:
            if path.exists(): errors.append(f"{path.relative_to(root)} must not exist when GIF preview is disabled")
    return errors
