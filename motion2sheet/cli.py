"""Compatibility facade for the canonical motion feature CLI."""

from .motion.cli import (
    build,
    main,
    package_root,
    parse_canvas,
    parser,
    resolve_profile,
    run_blender_extractor,
    validate,
)

__all__ = [
    "build",
    "main",
    "package_root",
    "parse_canvas",
    "parser",
    "resolve_profile",
    "run_blender_extractor",
    "validate",
]


if __name__ == "__main__":
    raise SystemExit(main())
