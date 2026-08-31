"""Generic Blender bootstrap for all anim2sheet animations."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load anim2sheet module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--output", required=True)
    args, unknown = parser.parse_known_args(argv())
    source = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    registry = _load_module("motion2sheet_anim2sheet_registry", ROOT / "registry.py")
    animation_name = str(source.get("animation", registry.DEFAULT_ANIMATION))
    animation = registry.get_animation(animation_name)
    author = _load_module(
        f"motion2sheet_anim2sheet_{animation_name}_author",
        ROOT / animation.blender_author,
    )
    author_args = source.get("blenderAuthorArgs", [])
    if not isinstance(author_args, list) or any(not isinstance(value, str) for value in author_args):
        raise RuntimeError("source blenderAuthorArgs must be a string array")
    forwarded = ["--spec", args.spec, *author_args, "--output", args.output, *unknown]
    old_argv = sys.argv
    try:
        sys.argv = [str(ROOT / "blender_entry.py"), "--", *forwarded]
        return int(author.main())
    finally:
        sys.argv = old_argv


if __name__ == "__main__":
    raise SystemExit(main())
