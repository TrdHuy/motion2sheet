from __future__ import annotations

import argparse
import subprocess
import sys

from .common.review.runner import run_review
from .registry import DEFAULT_ANIMATION, animation_names


def build(args) -> int:
    args.frames = None
    return run_review(args)


def review(args) -> int:
    return run_review(args)


def validate(args) -> int:
    from pathlib import Path
    import json
    root = Path(args.output)
    metadata_path = root / "metadata.json"
    if not metadata_path.is_file():
        raise RuntimeError("metadata.json is missing")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    required = ["source.json", "source.blend", "motion_debug.json", "camera_debug.json",
                "leg_ik_debug.json", "reopen_debug.json", "invocation.json", "resolved_config.json"]
    missing = [name for name in required if not (root / name).exists()]
    if missing:
        raise RuntimeError(f"anim2sheet output missing files: {missing}")
    if metadata.get("tool") != "anim2sheet":
        raise RuntimeError("metadata tool must be anim2sheet")
    print(f"anim2sheet: validation OK -> {root}")
    return 0


def _execution_args(parser: argparse.ArgumentParser, *, frames: bool) -> None:
    parser.add_argument("--animation", choices=animation_names(), default=DEFAULT_ANIMATION)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--joint-contract", required=True)
    parser.add_argument("--camera-profile", required=True)
    if frames:
        parser.add_argument("--frames", default=None)
    else:
        parser.set_defaults(frames=None)
    parser.add_argument("--cameras", default=None)
    parser.add_argument("--blender", default="blender")
    parser.add_argument("--output", required=True)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="anim2sheet")
    sub = root.add_subparsers(dest="command", required=True)
    build_parser = sub.add_parser("build")
    _execution_args(build_parser, frames=False)
    build_parser.set_defaults(func=build)
    review_parser = sub.add_parser("review")
    _execution_args(review_parser, frames=True)
    review_parser.set_defaults(func=review)
    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("output")
    validate_parser.set_defaults(func=validate)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, RuntimeError, subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        print(f"anim2sheet: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
