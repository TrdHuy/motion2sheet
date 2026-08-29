from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat


def _validate_frame_set(
    root: Path,
    folder: str,
    frames: int,
    canvas: tuple[int, int],
    *,
    require_alpha_content: bool,
) -> tuple[list[str], list[Path]]:
    errors: list[str] = []
    frame_paths = sorted((root / folder).glob("*.png"))
    if len(frame_paths) != frames:
        return [f"expected {frames} {folder} PNGs, got {len(frame_paths)}"], frame_paths

    changed = 0
    previous = None
    for path in frame_paths:
        with Image.open(path) as image:
            rgba = image.convert("RGBA")
            if rgba.size != canvas:
                errors.append(
                    f"{folder}/{path.name} has size {rgba.size}, expected {canvas}"
                )
            if require_alpha_content:
                alpha = rgba.getchannel("A")
                bbox = alpha.getbbox()
                if bbox is None:
                    errors.append(f"{folder}/{path.name} is fully transparent")
                elif (
                    bbox[0] <= 1
                    or bbox[1] <= 1
                    or bbox[2] >= canvas[0] - 1
                    or bbox[3] >= canvas[1] - 1
                ):
                    errors.append(f"{folder}/{path.name} touches canvas edge")
            if previous is not None:
                diff = ImageChops.difference(previous, rgba)
                if max(ImageStat.Stat(diff).sum) > 1.0:
                    changed += 1
            previous = rgba.copy()

    if frames > 1 and changed < frames - 3:
        errors.append(f"{folder} animation is too static")
    return errors, frame_paths


def _validate_sheet(
    path: Path,
    canvas: tuple[int, int],
    frames: int,
    columns: int,
    label: str,
) -> list[str]:
    if not path.exists():
        return [f"{label} is missing"]
    rows = (frames + columns - 1) // columns
    with Image.open(path) as image:
        errors = []
        if image.size != (canvas[0] * columns, canvas[1] * rows):
            errors.append(f"{label} dimensions do not match source contract")
        if image.mode != "RGBA":
            errors.append(f"{label} must be RGBA")
        return errors


def _validate_rig_exports(root: Path, metadata: dict) -> list[str]:
    errors = []
    expected = {
        "rig_default_overview.png": metadata.get("rigOverview"),
        "rig_default_labeled.png": metadata.get("rigLabeled"),
        "rig_bones.json": metadata.get("rigManifest"),
        "rig_bones.txt": metadata.get("rigHierarchy"),
    }
    for filename, declared in expected.items():
        if declared != filename:
            errors.append(f"metadata must reference {filename}")
        if not (root / filename).exists():
            errors.append(f"{filename} is missing")

    if errors:
        return errors

    try:
        manifest = json.loads((root / "rig_bones.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"rig_bones.json is invalid: {exc}"]

    if manifest.get("armature") != "GameHumanoidV2":
        errors.append("rig_bones.json armature must be GameHumanoidV2")
    bones = manifest.get("bones")
    if not isinstance(bones, list) or not bones:
        errors.append("rig_bones.json must contain bones")
    elif int(manifest.get("boneCount", -1)) != len(bones):
        errors.append("rig_bones.json boneCount mismatch")

    for filename in ("rig_default_overview.png", "rig_default_labeled.png"):
        try:
            with Image.open(root / filename) as image:
                if image.width < 512 or image.height < 512:
                    errors.append(f"{filename} must be at least 512x512")
        except OSError as exc:
            errors.append(f"{filename} is invalid: {exc}")
    return errors


def validate_output(root: Path) -> list[str]:
    errors: list[str] = []
    required = ["source.json", "metadata.json", "source.blend", "motion_debug.json"]
    for name in required:
        if not (root / name).exists():
            errors.append(f"{name} is missing")
    if errors:
        return errors

    source = json.loads((root / "source.json").read_text(encoding="utf-8"))
    metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    debug = json.loads((root / "motion_debug.json").read_text(encoding="utf-8"))
    frames = int(source["frames"])
    canvas = tuple(source["canvas"])
    columns = int(source["sheetColumns"])

    object_errors, _ = _validate_frame_set(
        root, "frames", frames, canvas, require_alpha_content=True
    )
    skeleton_errors, _ = _validate_frame_set(
        root, "skeleton_frames", frames, canvas, require_alpha_content=False
    )
    errors.extend(object_errors)
    errors.extend(skeleton_errors)

    errors.extend(
        _validate_sheet(
            root / "sprite_sheet.png",
            canvas,
            frames,
            columns,
            "sprite_sheet.png",
        )
    )
    errors.extend(
        _validate_sheet(
            root / "object_sheet.png",
            canvas,
            frames,
            columns,
            "object_sheet.png",
        )
    )
    errors.extend(
        _validate_sheet(
            root / "skeleton_sheet.png",
            canvas,
            frames,
            columns,
            "skeleton_sheet.png",
        )
    )

    if not (root / "preview.gif").exists():
        errors.append("preview.gif is missing")
    if metadata.get("visualPipeline") != "blender-native":
        errors.append("metadata visualPipeline must be blender-native")
    if metadata.get("blendSource") != "source.blend":
        errors.append("metadata blendSource must reference source.blend")
    if metadata.get("motionSolver") != "hybrid-fk-ik":
        errors.append("metadata motionSolver must be hybrid-fk-ik")
    if metadata.get("skeletonRenderer") != "blender-viewport-actual-armature":
        errors.append(
            "metadata skeletonRenderer must be blender-viewport-actual-armature"
        )
    if metadata.get("postRenderVisualProcessing") is not False:
        errors.append("post-render visual processing must be disabled")

    errors.extend(_validate_rig_exports(root, metadata))

    samples = debug.get("samples", [])
    if len(samples) != frames:
        errors.append("motion_debug sample count does not match frames")
    return errors
