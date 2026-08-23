from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from .decay import apply_decay_to_frames
from .packer import compose_sheet, write_preview
from .spec import VfxSpec, load_profile
from .stroke_bundle import apply_stroke_bundle_to_frames
from .validator import validate_output


def parse_canvas(value: str) -> tuple[int, int]:
    try:
        width, height = value.lower().split("x", 1)
        parsed = int(width), int(height)
    except (ValueError, AttributeError) as exc:
        raise argparse.ArgumentTypeError("canvas must look like 512x512") from exc
    if parsed[0] <= 0 or parsed[1] <= 0:
        raise argparse.ArgumentTypeError("canvas dimensions must be positive")
    return parsed


def package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def run_blender(spec_path: Path, output: Path, blender_name: str) -> None:
    blender = shutil.which(blender_name) if Path(blender_name).name == blender_name else blender_name
    if not blender:
        raise RuntimeError(f"Blender executable not found: {blender_name}")
    script = package_root() / "blender" / "generate_vfx.py"
    subprocess.run([
        str(blender), "--background", "--factory-startup", "--python", str(script), "--",
        "--spec", str(spec_path.resolve()), "--output", str(output.resolve()),
    ], check=True)


def build(args) -> int:
    profile = load_profile(Path(args.profile)) if args.profile else None
    spec = VfxSpec.create(
        template=args.template, variant=args.variant, frames=args.frames, fps=args.fps,
        canvas=args.canvas, sheet_columns=args.sheet_columns, seed=args.seed,
        overrides=args.set_values, profile=profile,
    )
    output = Path(args.output)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    source_path = output / "source.json"
    write_json(source_path, spec.to_dict())
    run_blender(source_path, output, args.blender)

    frame_paths = sorted((output / "frames").glob("*.png"))
    # Blender remains part of the deterministic build/toolchain contract, but
    # the approved 2D lightning slash silhouette is now rendered completely
    # from the shared EnergyGraph as tapered flow strokes. This intentionally
    # prevents Blender body geometry/radial spokes from leaking into final RGBA.
    apply_stroke_bundle_to_frames(frame_paths, spec.params, seed=spec.seed)
    # Residual shards remain a small secondary detail; the main F6-F8 topology
    # breakup already happens through independent per-stroke lifetimes.
    apply_decay_to_frames(frame_paths, spec.params, seed=spec.seed)
    compose_sheet(frame_paths, output / "vfx_sheet.png", columns=spec.sheet_columns)
    write_preview(frame_paths, output / "preview.gif", fps=spec.fps)
    metadata = {
        "tool": "vfx2sheet", "version": 1, "template": spec.template, "variant": spec.variant,
        "frames": spec.frames, "fps": spec.fps, "canvas": list(spec.canvas),
        "sheetColumns": spec.sheet_columns, "seed": spec.seed, "background": "transparent",
        "renderer": "blender-headless+shared-energy-graph+deterministic-stroke-bundle+embedded-lightning+per-stroke-decay",
        "profile": str(args.profile) if args.profile else None,
    }
    write_json(output / "metadata.json", metadata)
    errors = validate_output(output)
    if errors:
        raise RuntimeError("VFX validation failed:\n" + "\n".join(errors))
    print(f"vfx2sheet: build OK -> {output}")
    return 0


def validate(args) -> int:
    errors = validate_output(Path(args.output))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"vfx2sheet: validation OK -> {args.output}")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="vfx2sheet")
    sub = root.add_subparsers(dest="command", required=True)
    build_parser = sub.add_parser("build", help="Build a deterministic standalone VFX sprite sheet")
    build_parser.add_argument("--profile", help="JSON VFX profile/preset")
    build_parser.add_argument("--template", choices=("slash",))
    build_parser.add_argument("--variant", choices=("lightning",))
    build_parser.add_argument("--frames", type=int)
    build_parser.add_argument("--fps", type=int)
    build_parser.add_argument("--canvas", type=parse_canvas)
    build_parser.add_argument("--sheet-columns", type=int)
    build_parser.add_argument("--seed", type=int)
    build_parser.add_argument("--set", dest="set_values", action="append", default=[])
    build_parser.add_argument("--blender", default="blender")
    build_parser.add_argument("--output", required=True)
    build_parser.set_defaults(func=build)
    validate_parser = sub.add_parser("validate", help="Validate generated VFX output")
    validate_parser.add_argument("output")
    validate_parser.set_defaults(func=validate)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "build" and not args.profile and (not args.template or not args.variant):
            raise ValueError("build requires --profile or both --template and --variant")
        return args.func(args)
    except (RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"vfx2sheet: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())