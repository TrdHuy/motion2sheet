"""Generic Blender bootstrap for all vfx2sheet effects."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load vfx2sheet module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--spec", required=True)
    args, _unknown = parser.parse_known_args(argv())
    source = json.loads(Path(args.spec).read_text(encoding="utf-8"))

    registry = _load_module("motion2sheet_vfx2sheet_registry", ROOT / "registry.py")
    effect_name = str(source.get("effect", registry.DEFAULT_EFFECT))
    effect = registry.get_effect(effect_name)
    renderer_path = ROOT / effect.renderer
    renderer = _load_module(f"motion2sheet_vfx2sheet_{effect_name}_renderer", renderer_path)
    renderer.base.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
