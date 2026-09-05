from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from motion2sheet.motion.model_render.profile import load_camera_profile
from motion2sheet.motion.model_render.runner import compose_gif, compose_sheet
from motion2sheet.motion.roundtrip.schema import read_json, validate_animation_document, validate_rig_document
from motion2sheet.motion.skin import skin_statistics, validate_skin_document

from .fidelity import compare_source_to_humanoid_motion
from .mapping import mapping_diagnostics, read_mapping, validate_character_mapping
from .root_motion import humanoid_root_motion
from .schema import read_animation


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _blender(value: str) -> str:
    resolved = shutil.which(value) if Path(value).name == value else value
    if not resolved:
        raise RuntimeError(f"Blender executable not found: {value}")
    return str(resolved)


def _run_blender(script: str, blender: str, arguments: list[str]) -> None:
    path = Path(__file__).with_name(script)
    subprocess.run([_blender(blender), "--background", "--factory-startup", "--python-exit-code", "1", "--python", str(path), "--", *arguments], check=True)


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


def parse_samples(value: str, frame_count: int) -> list[int]:
    available = set(range(frame_count))
    if value.strip().lower() in {"all", "*"}:
        return list(range(frame_count))
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
        raise ValueError("--frames selected no Humanoid Motion samples")
    if len(set(selected)) != len(selected):
        raise ValueError("--frames contains duplicate Humanoid Motion samples")
    missing = [sample for sample in selected if sample not in available]
    if missing:
        raise ValueError(f"--frames contains samples outside 0..{frame_count - 1}: {missing}")
    return selected


def export_humanoid_animation(*, source_rig_path: Path, source_animation_path: Path, mapping_path: Path, animation_id: str, loop: bool, output: Path, blender: str = "blender") -> dict[str, Any]:
    source_rig_path = source_rig_path.resolve(); source_animation_path = source_animation_path.resolve(); mapping_path = mapping_path.resolve()
    for path in (source_rig_path, source_animation_path, mapping_path):
        if not path.is_file():
            raise ValueError(f"export-humanoid-animation input does not exist: {path}")
    rig = validate_rig_document(read_json(source_rig_path))
    source_animation = validate_animation_document(read_json(source_animation_path), rig)
    if "durationSeconds" not in source_animation:
        raise ValueError(
            "Source Animation is missing durationSeconds; re-export it with the current "
            "export-animation-json command"
        )
    mapping = validate_character_mapping(read_mapping(mapping_path), rig)
    output = output.resolve(); output.mkdir(parents=True, exist_ok=True)
    request = {"sourceRigPath": str(source_rig_path), "sourceAnimationPath": str(source_animation_path), "mappingPath": str(mapping_path), "animationId": animation_id, "loop": loop, "animationOutput": str(output / "animation.json"), "diagnosticsOutput": str(output / "diagnostics" / "export_blender.json")}
    _write_json(output / "diagnostics" / "export_request.json", request)
    _run_blender("blender_export.py", blender, ["--request", str(output / "diagnostics" / "export_request.json")])
    animation = read_animation(output / "animation.json")
    blender_diagnostics = json.loads((output / "diagnostics" / "export_blender.json").read_text(encoding="utf-8"))
    report = {
        "schema": "motion2sheet.humanoid-motion.export", "version": 1, "humanoidMotionSchema": animation["schema"], "animationId": animation["id"], "canonicalSkeleton": animation["canonicalSkeleton"], "durationSeconds": animation["durationSeconds"], "fps": animation["fps"], "frameCount": animation["frameCount"], "loop": animation["loop"], "animationSha256": sha256(output / "animation.json"),
        "sourceAuthorities": {"rigSha256": sha256(source_rig_path), "animationSha256": sha256(source_animation_path), "mappingSha256": sha256(mapping_path)},
        "semanticMapping": mapping_diagnostics(mapping, rig), "rootMotion": humanoid_root_motion(animation),
        "canonicalization": {"locomotionPolicy": blender_diagnostics["locomotionPolicy"], "sourcePlanarEndToEnd": blender_diagnostics["sourcePlanarEndToEnd"], "sourcePlanarDisplacement": blender_diagnostics["sourcePlanarDisplacement"], "strippedPlanarEndToEnd": blender_diagnostics["strippedPlanarEndToEnd"], "sourceHipsVerticalRange": blender_diagnostics["sourceHipsVerticalRange"], "canonicalHipsVerticalRange": blender_diagnostics["canonicalHipsVerticalRange"]},
        "sourceFbxRequired": False, "outputs": {"animation": "animation.json", "diagnostics": "diagnostics/"},
    }
    _write_json(output / "export.json", report)
    return report


def verify_humanoid_animation_fidelity(*, source_rig_path: Path, source_animation_path: Path, mapping_path: Path, animation_path: Path, output: Path) -> dict[str, Any]:
    paths = [path.resolve() for path in [source_rig_path, source_animation_path, mapping_path, animation_path]]
    source_rig_path, source_animation_path, mapping_path, animation_path = paths
    for path in paths:
        if not path.is_file():
            raise ValueError(f"verify-humanoid-animation-fidelity input does not exist: {path}")
    source_rig = validate_rig_document(read_json(source_rig_path)); source_animation = validate_animation_document(read_json(source_animation_path), source_rig); mapping = validate_character_mapping(read_mapping(mapping_path), source_rig)
    humanoid_motion = json.loads(animation_path.read_text(encoding="utf-8"))
    try:
        report = compare_source_to_humanoid_motion(source_rig, source_animation, mapping, humanoid_motion)
    except Exception as exc:
        report = {"schema": "motion2sheet.humanoid-motion.source-fidelity", "version": 1, "pass": False, "independentPath": "pure-python Motion JSON hierarchy/TRS evaluation; no Humanoid Motion exporter or playback imports", "failures": [f"independent fidelity evaluation failed: {exc}"]}
    report["authorities"] = {"sourceRigSha256": sha256(source_rig_path), "sourceAnimationSha256": sha256(source_animation_path), "sourceMappingSha256": sha256(mapping_path), "humanoidMotionAnimationSha256": sha256(animation_path)}
    output = output.resolve(); _write_json(output, report)
    if not report["pass"]:
        raise RuntimeError(f"Source -> Humanoid Motion fidelity failed; see {output}: {report['failures']}")
    return report


def render_humanoid_animation(*, model_path: Path, character_rig_path: Path, skin_path: Path, mapping_path: Path, animation_path: Path, camera_profile_path: Path, output: Path, sheet_columns: int = 8, canvas: tuple[int, int] = (320, 320), background: str = "transparent", gif: bool = False, frames: str = "all", render_samples: int = 16, blender: str = "blender") -> dict[str, Any]:
    if sheet_columns <= 0 or canvas[0] <= 0 or canvas[1] <= 0 or render_samples <= 0:
        raise ValueError("sheet columns, canvas dimensions and render samples must be positive")
    paths = [path.resolve() for path in [model_path, character_rig_path, skin_path, mapping_path, animation_path, camera_profile_path]]
    model_path, character_rig_path, skin_path, mapping_path, animation_path, camera_profile_path = paths
    for path in paths:
        if not path.is_file():
            raise ValueError(f"render-humanoid-animation input does not exist: {path}")
    rig = validate_rig_document(read_json(character_rig_path)); skin = validate_skin_document(read_json(skin_path), rig); mapping = validate_character_mapping(read_mapping(mapping_path), rig); animation = read_animation(animation_path); camera = load_camera_profile(camera_profile_path)
    selected = parse_samples(frames, animation["frameCount"])
    output = output.resolve(); output.mkdir(parents=True, exist_ok=True)
    frame_dir = output / ".frames"; shutil.rmtree(frame_dir, ignore_errors=True); frame_dir.mkdir(parents=True)
    before_sha = sha256(animation_path)
    request = {"modelPath": str(model_path), "characterRigPath": str(character_rig_path), "skinPath": str(skin_path), "mappingPath": str(mapping_path), "animationPath": str(animation_path), "animationSha256": before_sha, "camera": camera, "selectedSamples": selected, "selectedFrames": [sample + 1 for sample in selected], "canvas": list(canvas), "background": _background(background), "output": str(output), "skinWeightTolerance": 1e-8, "renderSamples": render_samples}
    request_path = output / "diagnostics" / "render_request.json"; _write_json(request_path, request)
    _run_blender("blender_render.py", blender, ["--request", str(request_path)])
    after_sha = sha256(animation_path)
    if before_sha != after_sha:
        raise RuntimeError("Humanoid Motion animation was mutated during playback")
    frame_paths = [frame_dir / f"frame_{sample + 1:04d}.png" for sample in selected]
    missing = [str(path) for path in frame_paths if not path.is_file()]
    if missing:
        raise RuntimeError(f"Humanoid Motion render missing frames: {missing[:4]}")
    layout = compose_sheet(frame_paths, output / "pose_sheet.png", sheet_columns, canvas)
    gif_timing = compose_gif(frame_paths, output / "preview.gif", float(animation["fps"])) if gif else None
    diagnostics = {name: json.loads((output / "diagnostics" / f"{name}.json").read_text(encoding="utf-8")) for name in ("model_identity", "skin_reconstruction", "semantic_mapping", "retarget", "playback", "root_motion", "contact")}
    if not diagnostics["skin_reconstruction"]["pass"] or not diagnostics["playback"]["pass"]:
        raise RuntimeError("Humanoid Motion runtime fidelity failed; see diagnostics")
    report = {
        "schema": "motion2sheet.humanoid-motion.render", "version": 1, "humanoidMotionSchema": animation["schema"], "animationId": animation["id"], "canonicalSkeleton": animation["canonicalSkeleton"], "durationSeconds": animation["durationSeconds"], "fps": animation["fps"], "frameCount": animation["frameCount"], "characterId": rig["id"], "mappingId": mapping["id"],
        "cameraProfile": {"id": camera["id"], "path": str(camera_profile_path)}, "cameraFollowsRoot": bool(camera.get("followRoot")), "animationSha256Before": before_sha, "animationSha256After": after_sha, "animationMutated": False, "sourceFbxRequired": False, "sourceRigRequired": False, "runtimeTransformsAreAnimationAuthority": False, "skinStatistics": skin_statistics(skin, rig), "renderedSamples": selected, "renderSamples": render_samples, "layout": {"cellSize": list(canvas), "sheetColumns": sheet_columns, **layout}, "gifTiming": gif_timing, "semanticMapping": diagnostics["semantic_mapping"], "rootMotion": diagnostics["root_motion"], "retarget": diagnostics["retarget"], "playback": diagnostics["playback"], "contact": diagnostics["contact"], "outputs": {"poseSheet": "pose_sheet.png", "previewGif": "preview.gif" if gif else None, "diagnostics": "diagnostics/"},
    }
    _write_json(output / "render.json", report); shutil.rmtree(frame_dir); return report
