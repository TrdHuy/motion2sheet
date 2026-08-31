from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from .common.output.validator import validate_output
from .common.review.runner import run_review


def build(args) -> int:
    args.frames = None
    return run_review(args, command="build")


def review(args) -> int:
    return run_review(args, command="review")


def validate(args) -> int:
    errors = validate_output(Path(args.output))
    if errors:
        raise RuntimeError("; ".join(errors))
    print(f"anim2sheet: validation OK -> {args.output}")
    return 0


def _execution_args(parser: argparse.ArgumentParser, *, frames: bool) -> None:
    parser.add_argument("--animation", default=None, help="Optional action-name assertion; implementation is resolved from rig profile")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--rig-profile", default=None, help="Optional override for animation profile rigProfile")
    parser.add_argument("--character-profile", default=None, help="Optional override for animation profile characterProfile")
    parser.add_argument("--joint-contract", default=None, help="Optional override for animation profile jointContract")
    parser.add_argument("--camera-profile", required=True)
    if frames:
        parser.add_argument("--frames", default=None)
    else:
        parser.set_defaults(frames=None)
    parser.add_argument("--cameras", default=None)
    parser.add_argument("--gif", action="store_true", help="Package rendered execution-frame PNGs into GIF previews")
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
