from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from .common.io import read_json, write_json, write_pose_sequence
from .normalize import normalize_projected_sequences
from .output import assert_valid_output, validate_output_directory
from .render import compose_sheet, render_sequence
from .retarget import load_profile


def parse_canvas(value: str) -> tuple[int, int]:
    try:
        width, height = value.lower().split("x", 1)
        parsed = (int(width), int(height))
    except (ValueError, AttributeError) as exc:
        raise argparse.ArgumentTypeError("canvas must look like 320x320") from exc
    if parsed[0] <= 0 or parsed[1] <= 0:
        raise argparse.ArgumentTypeError("canvas dimensions must be positive")
    return parsed


def package_root() -> Path:
    return Path(__file__).resolve().parent


def resolve_profile(value: str) -> tuple[str, Path | None]:
    normalized = value.strip()
    if normalized.lower() == "source":
        return "source", None
    built_in = package_root() / "profiles" / f"{normalized}.json"
    if built_in.exists():
        profile = load_profile(built_in)
        return profile["name"], built_in
    explicit = Path(normalized)
    if explicit.exists():
        profile = load_profile(explicit)
        return profile["name"], explicit.resolve()
    raise RuntimeError(
        f"Unknown proportion profile {value!r}. Use 'source', a built-in profile name, or a JSON profile path."
    )


def run_blender_extractor(args, raw_path: Path, profile_path: Path | None) -> None:
    blender = shutil.which(args.blender) if Path(args.blender).name == args.blender else args.blender
    if not blender:
        raise RuntimeError(f"Blender executable not found: {args.blender}")
    script = package_root() / "extract" / "blender.py"
    command = [
        str(blender), "--background", "--factory-startup", "--python", str(script), "--",
        "--input", str(Path(args.input).resolve()), "--output", str(raw_path), "--frames", str(args.frames),
        "--directions", args.directions, "--camera-elevation", str(args.camera_elevation),
    ]
    if args.action:
        command.extend(["--action", args.action])
    if profile_path is not None:
        command.extend(["--profile-file", str(profile_path)])
    subprocess.run(command, check=True)


def build(args) -> int:
    input_path = Path(args.input)
    if not input_path.exists():
        raise RuntimeError(f"Input motion file does not exist: {input_path}")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    raw_path = output / ".raw_projected.json"
    profile_name, profile_path = resolve_profile(args.profile)
    run_blender_extractor(args, raw_path, profile_path)
    raw = read_json(raw_path)
    action = args.action or raw["action"]
    directions = [item.strip().lower() for item in args.directions.split(",") if item.strip()]
    normalized = normalize_projected_sequences(
        {direction: raw["directions"][direction] for direction in directions},
        action=action, canvas=args.canvas, padding=args.padding,
    )
    for direction, sequence in normalized.items():
        direction_dir = output / direction
        write_pose_sequence(direction_dir / "pose.json", sequence)
        frame_paths = render_sequence(sequence, direction_dir / "frames")
        compose_sheet(frame_paths, direction_dir / "pose_sheet.png", columns=args.sheet_columns)
    metadata = {
        "tool": "motion2sheet", "version": 1, "source": str(input_path), "action": action,
        "frames": args.frames, "directions": directions, "canvas": list(args.canvas),
        "sheetColumns": args.sheet_columns, "cameraElevation": args.camera_elevation,
        "proportionProfile": profile_name, "retarget": raw.get("retarget", {"profile": "source"}),
        "normalization": {
            "globalScaleAcrossDirections": True,
            "groundAnchor": "pelvis-x + lowest-ankle-y",
            "perFrameResize": False,
        },
        "sourceBoneMap": raw.get("boneMap", {}),
    }
    write_json(output / "metadata.json", metadata)
    if not args.keep_raw:
        raw_path.unlink(missing_ok=True)
    assert_valid_output(output)
    print(f"motion2sheet: build OK -> {output}")
    return 0


def validate(args) -> int:
    errors = validate_output_directory(Path(args.output))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"motion2sheet: validation OK -> {args.output}")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="motion2sheet")
    sub = root.add_subparsers(dest="command", required=True)
    build_parser = sub.add_parser("build", help="Extract motion and build canonical pose sheets")
    build_parser.add_argument("input")
    build_parser.add_argument("--frames", type=int, default=8)
    build_parser.add_argument("--directions", default="down")
    build_parser.add_argument("--canvas", type=parse_canvas, default=(320, 320))
    build_parser.add_argument("--output", required=True)
    build_parser.add_argument("--action", default=None)
    build_parser.add_argument("--blender", default="blender")
    build_parser.add_argument("--camera-elevation", type=float, default=35.0)
    build_parser.add_argument("--sheet-columns", type=int, default=4)
    build_parser.add_argument("--padding", type=int, default=20)
    build_parser.add_argument("--profile", default="source", help="Body proportion profile: source (default), built-in name such as chibi_v1, or JSON path")
    build_parser.add_argument("--keep-raw", action="store_true")
    build_parser.set_defaults(func=build)
    validate_parser = sub.add_parser("validate", help="Validate an existing generated output directory")
    validate_parser.add_argument("output")
    validate_parser.set_defaults(func=validate)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except (RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"motion2sheet: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
