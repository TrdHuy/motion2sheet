from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image

from motion2sheet.motion.roundtrip.schema import read_json, validate_rig_document
from motion2sheet.motion.skin import skin_statistics, validate_skin_document

GIF_TIME_QUANTUM_MS = 10


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
