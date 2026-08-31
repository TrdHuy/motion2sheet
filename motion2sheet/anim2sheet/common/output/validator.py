from __future__ import annotations

import json
from pathlib import Path


REQUIRED_JSON = (
    "source.json",
    "metadata.json",
    "invocation.json",
    "resolved_config.json",
    "motion_debug.json",
    "camera_debug.json",
    "leg_ik_debug.json",
    "reopen_debug.json",
)
REQUIRED_FILES = (*REQUIRED_JSON, "source.blend")


def _read_json(path: Path, errors: list[str]) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path.name} is invalid: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{path.name} must contain a JSON object")
        return {}
    return value


def _frames(values) -> list[int]:
    return [int(value) for value in values]


def validate_output(root: Path) -> list[str]:
    errors: list[str] = []
    missing = [name for name in REQUIRED_FILES if not (root / name).exists()]
    if missing:
        return [f"{name} is missing" for name in missing]

    data = {name: _read_json(root / name, errors) for name in REQUIRED_JSON}
    if errors:
        return errors

    metadata = data["metadata.json"]
    invocation = data["invocation.json"]
    resolved = data["resolved_config.json"]
    motion = data["motion_debug.json"]
    camera = data["camera_debug.json"]
    leg = data["leg_ik_debug.json"]
    reopen = data["reopen_debug.json"]

    if metadata.get("tool") != "anim2sheet":
        errors.append("metadata tool must be anim2sheet")
    if invocation.get("tool") != "anim2sheet":
        errors.append("invocation tool must be anim2sheet")
    if invocation.get("command") not in {"build", "review"}:
        errors.append("invocation command must be build or review")
    if metadata.get("animation") != invocation.get("animation"):
        errors.append("metadata animation does not match invocation")
    if resolved.get("animation") != invocation.get("animation"):
        errors.append("resolved animation does not match invocation")

    try:
        contract_frames = _frames(invocation.get("contractFrames", []))
        execution_frames = _frames(invocation.get("executionFrames", []))
    except (TypeError, ValueError):
        return errors + ["invocation frame lists must contain integers"]
    if not contract_frames:
        errors.append("invocation contractFrames is empty")
    if not execution_frames:
        errors.append("invocation executionFrames is empty")
    if any(frame not in contract_frames for frame in execution_frames):
        errors.append("executionFrames must be a subset of contractFrames")

    frame_sources = {
        "metadata": metadata.get("reviewFrames", []),
        "resolved_config": resolved.get("executionFrames", []),
        "camera_debug": camera.get("reviewFrames", []),
        "leg_ik_debug": leg.get("frames", []),
        "reopen_debug": reopen.get("frames", []),
        "motion_debug": [row.get("frame") for row in motion.get("samples", [])],
    }
    for label, values in frame_sources.items():
        try:
            actual = _frames(values)
        except (TypeError, ValueError):
            errors.append(f"{label} frame list is invalid")
            continue
        if actual != execution_frames:
            errors.append(f"{label} frames do not match invocation executionFrames")

    if _frames(resolved.get("contractFrames", [])) != contract_frames:
        errors.append("resolved_config contractFrames do not match invocation")

    cameras = list(invocation.get("cameras", []))
    if not cameras:
        errors.append("invocation cameras is empty")
    if list(metadata.get("reviewCameras", [])) != cameras:
        errors.append("metadata cameras do not match invocation")
    if list(resolved.get("cameras", [])) != cameras:
        errors.append("resolved_config cameras do not match invocation")
    if list(camera.get("selectedCameras", [])) != cameras:
        errors.append("camera_debug cameras do not match invocation")

    for camera_name in cameras:
        camera_root = root / "cameras" / camera_name
        for frame in execution_frames:
            for folder in ("frames", "skeleton_frames", "overlay_frames"):
                if not (camera_root / folder / f"{frame:02d}.png").is_file():
                    errors.append(f"missing {camera_name}/{folder}/F{frame}")
        for name in ("object_keyposes.png", "skeleton_keyposes.png", "object_skeleton_overlay.png"):
            if not (camera_root / name).is_file():
                errors.append(f"missing {camera_name}/{name}")

    for name in ("object_keyposes.png", "skeleton_keyposes.png", "object_skeleton_overlay.png"):
        if not (root / name).is_file():
            errors.append(f"{name} is missing")
    return errors
