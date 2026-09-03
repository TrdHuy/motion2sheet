from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image

from motion2sheet.motion.roundtrip.schema import read_json, validate_animation_document, validate_rig_document
from motion2sheet.motion.skin import (
    diagnose_level1_rig_compatibility,
    skin_statistics,
    validate_level1_rig_compatibility,
    validate_skin_document,
)

from .profile import load_camera_profile

GIF_TIME_QUANTUM_MS = 10


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _blender_executable(value: str) -> str:
    resolved = shutil.which(value) if Path(value).name == value else value
    if not resolved:
        raise RuntimeError(f"Blender executable not found: {value}")
    return str(resolved)


def _run_blender(script_name: str, blender: str, arguments: list[str]) -> None:
    script = Path(__file__).with_name(script_name)
    subprocess.run(
        [_blender_executable(blender), "--background", "--factory-startup", "--python-exit-code", "1", "--python", str(script), "--", *arguments],
        check=True,
    )


def _background(value: str) -> dict[str, Any]:
    if value == "transparent":
        return {"transparent": True, "rgba": [0.0, 0.0, 0.0, 0.0]}
    if len(value) == 7 and value.startswith("#"):
        try:
            rgb = [int(value[index:index + 2], 16) / 255.0 for index in (1, 3, 5)]
        except ValueError as exc:
            raise ValueError("background must be transparent or #RRGGBB") from exc
        return {"transparent": False, "rgba": [*rgb, 1.0]}
    raise ValueError("background must be transparent or #RRGGBB")


def parse_frames(value: str, animation: dict[str, Any]) -> list[int]:
    available = [int(row["frame"]) for row in animation["frames"]]
    available_set = set(available)
    if value.strip().lower() in {"all", "*"}:
        return available
    selected: list[int] = []
    for token in value.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            first, last = token.split("-", 1)
            start, end = int(first), int(last)
            step = 1 if end >= start else -1
            selected.extend(range(start, end + step, step))
        else:
            selected.append(int(token))
    if not selected:
        raise ValueError("--frames selected no frames")
    if len(set(selected)) != len(selected):
        raise ValueError("--frames contains duplicate frames")
    missing = [frame for frame in selected if frame not in available_set]
    if missing:
        raise ValueError(f"--frames contains frames outside Contract B: {missing}")
    return selected


def gif_frame_durations_ms(frame_count: int, fps: float) -> list[int]:
    if frame_count <= 0 or not math.isfinite(fps) or fps <= 0:
        raise ValueError("GIF frame count/FPS must be positive")
    boundaries = []
    for index in range(frame_count + 1):
        ideal_ms = index * 1000.0 / fps
        boundaries.append(int(math.floor(ideal_ms / GIF_TIME_QUANTUM_MS + 0.5)) * GIF_TIME_QUANTUM_MS)
    durations = [boundaries[index + 1] - boundaries[index] for index in range(frame_count)]
    if any(duration < GIF_TIME_QUANTUM_MS for duration in durations):
        raise ValueError(f"GIF timing cannot represent {fps:g} FPS without zero-duration frames")
    return durations


def compose_sheet(frame_paths: list[Path], output: Path, columns: int, canvas: tuple[int, int]) -> dict[str, Any]:
    rows = (len(frame_paths) + columns - 1) // columns
    sheet = Image.new("RGBA", (columns * canvas[0], rows * canvas[1]), (0, 0, 0, 0))
    try:
        for index, path in enumerate(frame_paths):
            with Image.open(path) as image:
                sheet.alpha_composite(image.convert("RGBA"), ((index % columns) * canvas[0], (index // columns) * canvas[1]))
        sheet.save(output)
        return {"sheetRows": rows, "sheetSize": list(sheet.size)}
    finally:
        sheet.close()


def compose_gif(frame_paths: list[Path], output: Path, fps: float) -> dict[str, Any]:
    durations = gif_frame_durations_ms(len(frame_paths), fps)
    images = [Image.open(path).convert("RGBA") for path in frame_paths]
    try:
        images[0].save(output, save_all=True, append_images=images[1:], duration=durations, loop=0, disposal=2, optimize=False)
    finally:
        for image in images:
            image.close()
    total = sum(durations)
    return {
        "frameDurationsMs": durations,
        "totalDurationMs": total,
        "effectiveFps": len(durations) * 1000.0 / total,
        "quantumMs": GIF_TIME_QUANTUM_MS,
    }


def _validate_and_record_level1_compatibility(
    animation_rig: dict[str, Any],
    character_rig: dict[str, Any],
    output: Path,
) -> dict[str, Any]:
    diagnostic = diagnose_level1_rig_compatibility(animation_rig, character_rig)
    _write_json(output / "diagnostics" / "rig_compatibility.json", diagnostic)
    try:
        return validate_level1_rig_compatibility(animation_rig, character_rig)
    except ValueError as exc:
        summary = {
            "missingBoneCount": len(diagnostic["missingBones"]),
            "extraBoneCount": len(diagnostic["extraBones"]),
            "parentMismatchCount": len(diagnostic["parentMismatches"]),
            "coordinateMismatchCount": len(diagnostic["coordinateMismatches"]),
            "restBasisMismatchCount": diagnostic["restBasisMismatchCount"],
            "maxRestBasisErrorDegrees": diagnostic["maxRestBasisErrorDegrees"],
            "worstRestBasisBone": diagnostic["worstRestBasisBone"],
            "restBasisToleranceDegrees": diagnostic["restBasisToleranceDegrees"],
            "retargeting": diagnostic["retargeting"],
            "fuzzyMapping": diagnostic["fuzzyMapping"],
        }
        raise ValueError(f"{exc}; Level-1 diagnostic summary={json.dumps(summary, sort_keys=True)}") from exc


def export_character(*, input_path: Path, output: Path, blender: str = "blender") -> dict[str, Any]:
    input_path = input_path.resolve()
    if not input_path.is_file() or input_path.suffix.lower() != ".fbx":
        raise ValueError("export-character requires an existing FBX source")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    _run_blender("blender_export_character.py", blender, ["--input", str(input_path), "--output", str(output)])
    model_path = output / "model.glb"
    rig_path = output / "rig.json"
    skin_path = output / "skin.json"
    report_path = output / "diagnostics" / "export.json"
    for path in (model_path, rig_path, skin_path, report_path):
        if not path.is_file():
            raise RuntimeError(f"export-character did not produce {path.name}")
    rig = read_json(rig_path)
    skin = read_json(skin_path)
    validate_rig_document(rig)
    validate_skin_document(skin, rig)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if _sha256(input_path) != report["sourceSha256"]:
        raise RuntimeError("export-character source SHA diagnostic mismatch")
    if _sha256(model_path) != skin["model"]["sha256"]:
        raise RuntimeError("export-character model SHA does not match skin.json")
    stats = skin_statistics(skin, rig)
    if min(stats["meshCount"], stats["vertexCount"], stats["weightedVertexCount"], stats["influenceCount"], stats["boneCount"]) <= 0:
        raise RuntimeError(f"export-character produced empty skin authority: {stats}")
    if stats["unknownBoneReferences"] != 0:
        raise RuntimeError(f"export-character produced unknown skin bones: {stats}")
    return report


def render_model_animation(
    *,
    model_path: Path,
    character_rig_path: Path,
    skin_path: Path,
    animation_rig_path: Path,
    animation_path: Path,
    camera_profile_path: Path,
    output: Path,
    sheet_columns: int = 8,
    canvas: tuple[int, int] = (320, 320),
    background: str = "transparent",
    gif: bool = False,
    frames: str = "all",
    blender: str = "blender",
) -> dict[str, Any]:
    if sheet_columns <= 0 or canvas[0] <= 0 or canvas[1] <= 0:
        raise ValueError("sheet columns and canvas dimensions must be positive")
    model_path = model_path.resolve()
    character_rig_path = character_rig_path.resolve()
    skin_path = skin_path.resolve()
    animation_rig_path = animation_rig_path.resolve()
    animation_path = animation_path.resolve()
    camera_profile_path = camera_profile_path.resolve()
    output = output.resolve()
    for path in (model_path, character_rig_path, skin_path, animation_rig_path, animation_path, camera_profile_path):
        if not path.is_file():
            raise ValueError(f"render-model-animation input does not exist: {path}")
    character_rig = read_json(character_rig_path)
    animation_rig = read_json(animation_rig_path)
    animation = read_json(animation_path)
    skin = read_json(skin_path)
    validate_rig_document(character_rig)
    validate_rig_document(animation_rig)
    validate_animation_document(animation, animation_rig)
    validate_skin_document(skin, character_rig)
    output.mkdir(parents=True, exist_ok=True)
    compatibility = _validate_and_record_level1_compatibility(animation_rig, character_rig, output)
    camera = load_camera_profile(camera_profile_path)
    selected = parse_frames(frames, animation)
    frame_dir = output / ".frames"
    shutil.rmtree(frame_dir, ignore_errors=True)
    frame_dir.mkdir(parents=True)
    request = {
        "modelPath": str(model_path),
        "characterRigPath": str(character_rig_path),
        "skinPath": str(skin_path),
        "animationRigPath": str(animation_rig_path),
        "animationPath": str(animation_path),
        "camera": camera,
        "compatibility": compatibility,
        "selectedFrames": selected,
        "canvas": list(canvas),
        "background": _background(background),
        "output": str(output),
        "skinWeightTolerance": 1e-8,
    }
    request_path = output / "diagnostics" / "render_request.json"
    _write_json(request_path, request)
    _run_blender("blender_render_model.py", blender, ["--request", str(request_path)])
    frame_paths = [frame_dir / f"frame_{frame:04d}.png" for frame in selected]
    missing = [str(path) for path in frame_paths if not path.is_file()]
    if missing:
        raise RuntimeError(f"Blender real-model render missing frames: {missing[:4]}")
    layout = compose_sheet(frame_paths, output / "pose_sheet.png", sheet_columns, canvas)
    gif_timing = compose_gif(frame_paths, output / "preview.gif", float(animation["fps"])) if gif else None
    skin_reconstruction = json.loads((output / "diagnostics" / "skin_reconstruction.json").read_text(encoding="utf-8"))
    playback = json.loads((output / "diagnostics" / "playback.json").read_text(encoding="utf-8"))
    model_identity = json.loads((output / "diagnostics" / "model_identity.json").read_text(encoding="utf-8"))
    if not skin_reconstruction.get("pass"):
        raise RuntimeError(f"skin reconstruction fidelity failed: {skin_reconstruction}")
    if not playback.get("pass"):
        raise RuntimeError(f"Contract B playback fidelity failed: {playback}")
    report = {
        "schema": "motion2sheet.model-animation-render",
        "version": 1,
        "motionAuthority": "animation.json",
        "modelAuthority": "model.glb",
        "rigAuthority": "character_rig.json",
        "skinAuthority": "skin.json",
        "sourceFbxRequired": False,
        "characterRig": {"id": character_rig["id"], "boneCount": len(character_rig["bones"])},
        "animationRig": {"id": animation_rig["id"], "boneCount": len(animation_rig["bones"])},
        "animation": {"id": animation["id"], "frameCount": animation["frameCount"], "fps": animation["fps"]},
        "cameraProfile": {"id": camera["id"], "path": str(camera_profile_path)},
        "rigCompatibility": compatibility,
        "skinStatistics": skin_statistics(skin, character_rig),
        "modelIdentity": model_identity,
        "skinReconstruction": skin_reconstruction,
        "animationFidelity": playback,
        "renderedFrames": selected,
        "frameCount": len(selected),
        "layout": {"cellSize": list(canvas), "sheetColumns": sheet_columns, **layout},
        "transparentBackground": bool(request["background"]["transparent"]),
        "gifTiming": gif_timing,
        "outputs": {
            "poseSheet": "pose_sheet.png",
            "previewGif": "preview.gif" if gif else None,
            "sourceBlend": "source.blend",
            "diagnostics": "diagnostics/",
        },
    }
    _write_json(output / "render.json", report)
    shutil.rmtree(frame_dir, ignore_errors=True)
    return report
