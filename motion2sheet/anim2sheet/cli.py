from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import json5

from .common.output.packer import compose_sheet, write_preview
from .common.output.validator import validate_output


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def load_profile(path: Path) -> dict:
    data = json5.loads(path.read_text(encoding="utf-8"))
    required = {"action", "frames", "fps", "canvas", "sheetColumns", "phases", "poseReference"}
    missing = required - set(data)
    if missing:
        raise ValueError(f"profile missing fields: {sorted(missing)}")
    return data


def load_pose_reference(profile_path: Path, reference_value: str, expected_frames: int) -> tuple[Path, dict]:
    reference_path = Path(reference_value)
    if not reference_path.is_absolute():
        reference_path = profile_path.parent / reference_path
    reference_path = reference_path.resolve()
    if not reference_path.is_file():
        raise ValueError(f"pose reference not found: {reference_path}")
    data = json.loads(reference_path.read_text(encoding="utf-8"))
    poses = data.get("keyPoses")
    if not isinstance(poses, list) or len(poses) != expected_frames:
        raise ValueError(f"pose reference must contain exactly {expected_frames} keyPoses")
    frames = [int(row.get("frame", -1)) for row in poses]
    expected = list(range(1, expected_frames + 1))
    if frames != expected:
        raise ValueError(f"pose reference frame order must be {expected}, got {frames}")
    return reference_path, data


def run_blender(source: Path, output: Path, blender_name: str) -> None:
    blender = shutil.which(blender_name) if Path(blender_name).name == blender_name else blender_name
    if not blender:
        raise RuntimeError(f"Blender executable not found: {blender_name}")
    script = Path(__file__).resolve().with_name("blender_entry.py")
    subprocess.run(
        [str(blender), "--background", "--factory-startup", "--python", str(script), "--",
         "--spec", str(source.resolve()), "--output", str(output.resolve())],
        check=True,
    )


def build(args) -> int:
    profile_path = Path(args.profile).resolve()
    profile = load_profile(profile_path)
    reference_path, reference = load_pose_reference(
        profile_path, str(profile["poseReference"]), int(profile["frames"])
    )
    output = Path(args.output)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    source = dict(profile)
    source["generator"] = "reference-driven-humanoid-poc-v2"
    source["poseReferenceSource"] = str(reference_path)
    source["poseReferenceData"] = reference
    source_path = output / "source.json"
    write_json(source_path, source)
    write_json(output / "pose_reference.json", reference)
    run_blender(source_path, output, args.blender)
    frames = sorted((output / "frames").glob("*.png"))
    compose_sheet(frames, output / "sprite_sheet.png", columns=int(source["sheetColumns"]))
    write_preview(frames, output / "preview.gif", fps=int(source["fps"]))
    write_json(output / "metadata.json", {
        "tool": "anim2sheet", "version": 2, "action": source["action"],
        "frames": source["frames"], "fps": source["fps"], "canvas": source["canvas"],
        "sheetColumns": source["sheetColumns"], "background": "transparent",
        "renderer": "blender-native-reference-driven-humanoid-poc-v2",
        "visualPipeline": "blender-native", "blendSource": "source.blend",
        "poseReference": "pose_reference.json", "poseReferenceAuthority": "pose-motion-only",
        "postRenderVisualProcessing": False, "profile": str(args.profile),
    })
    errors = validate_output(output)
    if errors:
        raise RuntimeError("animation validation failed:\n" + "\n".join(errors))
    print(f"anim2sheet: build OK -> {output}")
    return 0


def validate(args) -> int:
    errors = validate_output(Path(args.output))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"anim2sheet: validation OK -> {args.output}")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="anim2sheet")
    sub = root.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="Build Blender-native reference-driven character animation sheet")
    b.add_argument("--profile", required=True)
    b.add_argument("--blender", default="blender")
    b.add_argument("--output", required=True)
    b.set_defaults(func=build)
    v = sub.add_parser("validate")
    v.add_argument("output")
    v.set_defaults(func=validate)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"anim2sheet: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
