from __future__ import annotations

import shutil
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def move(src: str, dst: str) -> None:
    source = ROOT / src
    target = ROOT / dst
    if not source.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    shutil.move(str(source), str(target))


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")


def replace_text(path: Path, replacements: dict[str, str]) -> None:
    if not path.exists() or not path.is_file():
        return
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return
    updated = content
    for old, new in replacements.items():
        updated = updated.replace(old, new)
    if updated != content:
        path.write_text(updated, encoding="utf-8")


def main() -> int:
    old_vfx = ROOT / "motion2sheet/vfx"
    if not old_vfx.exists():
        print("vfx2sheet architecture already refactored")
        return 0

    # Runtime feature boundary.
    move("motion2sheet/vfx/cli.py", "motion2sheet/vfx2sheet/cli.py")
    move("motion2sheet/vfx/spec.py", "motion2sheet/vfx2sheet/effects/splash/config.py")
    move("motion2sheet/vfx/trajectory_config.py", "motion2sheet/vfx2sheet/common/trajectory/config.py")
    move("motion2sheet/blender/vfx_trajectory.py", "motion2sheet/vfx2sheet/common/trajectory/blender.py")
    move("motion2sheet/vfx/packer.py", "motion2sheet/vfx2sheet/common/output/packer.py")
    move("motion2sheet/vfx/validator.py", "motion2sheet/vfx2sheet/common/output/validator.py")
    move("motion2sheet/blender/native_generate_vfx.py", "motion2sheet/vfx2sheet/effects/splash/blender/renderer.py")

    # The accepted renderer is Blender-native and self-contained. These files are
    # historical PIL/prototype stages and are no longer on the production path.
    if old_vfx.exists():
        shutil.rmtree(old_vfx)
    legacy_generator = ROOT / "motion2sheet/blender/generate_vfx.py"
    if legacy_generator.exists():
        legacy_generator.unlink()

    # Stable package boundaries. Do not create empty common abstractions until a
    # second effect actually needs them.
    for package in (
        "motion2sheet/vfx2sheet/__init__.py",
        "motion2sheet/vfx2sheet/common/__init__.py",
        "motion2sheet/vfx2sheet/common/output/__init__.py",
        "motion2sheet/vfx2sheet/common/trajectory/__init__.py",
        "motion2sheet/vfx2sheet/effects/__init__.py",
        "motion2sheet/vfx2sheet/effects/splash/__init__.py",
        "motion2sheet/vfx2sheet/effects/splash/blender/__init__.py",
    ):
        write(package, '"""vfx2sheet package."""\n')

    write(
        "motion2sheet/vfx2sheet/registry.py",
        '''
        from __future__ import annotations

        from dataclasses import dataclass


        @dataclass(frozen=True)
        class EffectDefinition:
            name: str
            runtime_module: str
            renderer: str


        DEFAULT_EFFECT = "splash"

        _EFFECTS = {
            "splash": EffectDefinition(
                name="splash",
                runtime_module="motion2sheet.vfx2sheet.effects.splash.effect",
                renderer="effects/splash/blender/renderer.py",
            ),
        }


        def effect_names() -> tuple[str, ...]:
            return tuple(sorted(_EFFECTS))


        def get_effect(name: str) -> EffectDefinition:
            try:
                return _EFFECTS[name]
            except KeyError as exc:
                raise ValueError(f"Unsupported VFX effect: {name}") from exc
        ''',
    )

    write(
        "motion2sheet/vfx2sheet/effects/splash/effect.py",
        '''
        from __future__ import annotations

        from pathlib import Path
        from typing import Any

        from .config import VfxSpec, load_profile as _load_profile


        EFFECT_NAME = "splash"


        def load_profile(path: Path) -> dict[str, Any]:
            return _load_profile(path)


        def create_spec(**kwargs) -> VfxSpec:
            return VfxSpec.create(**kwargs)
        ''',
    )

    write(
        "motion2sheet/vfx2sheet/blender_entry.py",
        '''
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
        ''',
    )

    # Renderer keeps the accepted visual implementation byte-for-byte inside its
    # frozen payload; only the editable trajectory source location changes.
    renderer_path = ROOT / "motion2sheet/vfx2sheet/effects/splash/blender/renderer.py"
    renderer = renderer_path.read_text(encoding="utf-8")
    old_trajectory_line = 'trajectory_path = Path(__file__).with_name("vfx_trajectory.py").resolve()'
    new_trajectory_line = 'trajectory_path = (Path(__file__).resolve().parents[3] / "common" / "trajectory" / "blender.py").resolve()'
    if old_trajectory_line not in renderer:
        raise RuntimeError("Unable to locate renderer trajectory seam")
    renderer = renderer.replace(old_trajectory_line, new_trajectory_line, 1)
    renderer = renderer.replace(
        "Trajectory math remains editable in ``vfx_trajectory.py``.",
        "Trajectory math remains editable in ``common/trajectory/blender.py``.",
        1,
    )
    renderer_path.write_text(renderer, encoding="utf-8")

    write(
        "motion2sheet/vfx2sheet/cli.py",
        '''
        from __future__ import annotations

        import argparse
        import importlib
        import json
        import shutil
        import subprocess
        import sys
        from pathlib import Path

        from .common.output.packer import compose_sheet, write_preview
        from .common.output.validator import validate_output
        from .common.trajectory.config import load_trajectory_config, validate_trajectory_config
        from .registry import DEFAULT_EFFECT, effect_names, get_effect


        def parse_canvas(value: str) -> tuple[int, int]:
            try:
                width, height = value.lower().split("x", 1)
                parsed = int(width), int(height)
            except (ValueError, AttributeError) as exc:
                raise argparse.ArgumentTypeError("canvas must look like 512x512") from exc
            if parsed[0] <= 0 or parsed[1] <= 0:
                raise argparse.ArgumentTypeError("canvas dimensions must be positive")
            return parsed


        def write_json(path: Path, data: dict) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2) + "\\n", encoding="utf-8")


        def run_blender(spec_path: Path, output: Path, blender_name: str) -> None:
            blender = shutil.which(blender_name) if Path(blender_name).name == blender_name else blender_name
            if not blender:
                raise RuntimeError(f"Blender executable not found: {blender_name}")
            script = Path(__file__).resolve().with_name("blender_entry.py")
            subprocess.run([
                str(blender), "--background", "--factory-startup", "--python", str(script), "--",
                "--spec", str(spec_path.resolve()), "--output", str(output.resolve()),
            ], check=True)


        def resolve_trajectory(args, profile: dict | None) -> dict | None:
            if args.trajectory_config:
                return load_trajectory_config(Path(args.trajectory_config))
            if profile and "trajectory" in profile:
                return validate_trajectory_config(profile["trajectory"])
            return None


        def _effect_runtime(effect_name: str):
            definition = get_effect(effect_name)
            return definition, importlib.import_module(definition.runtime_module)


        def build(args) -> int:
            effect, runtime = _effect_runtime(args.effect)
            profile = runtime.load_profile(Path(args.profile)) if args.profile else None
            if profile and profile.get("effect") not in (None, effect.name):
                raise ValueError(
                    f"Profile effect {profile['effect']!r} does not match --effect {effect.name!r}"
                )
            trajectory = resolve_trajectory(args, profile)
            spec = runtime.create_spec(
                template=args.template, variant=args.variant, frames=args.frames, fps=args.fps,
                canvas=args.canvas, sheet_columns=args.sheet_columns, seed=args.seed,
                overrides=args.set_values, profile=profile,
            )
            output = Path(args.output)
            if output.exists():
                shutil.rmtree(output)
            output.mkdir(parents=True)
            source_path = output / "source.json"
            source = spec.to_dict()
            source["effect"] = effect.name
            if trajectory is not None:
                source["trajectory"] = trajectory
            write_json(source_path, source)
            run_blender(source_path, output, args.blender)
            frame_paths = sorted((output / "frames").glob("*.png"))
            compose_sheet(frame_paths, output / "vfx_sheet.png", columns=spec.sheet_columns)
            write_preview(frame_paths, output / "preview.gif", fps=spec.fps)
            metadata = {
                "tool": "vfx2sheet", "version": 48, "effect": effect.name,
                "template": spec.template, "variant": spec.variant,
                "frames": spec.frames, "fps": spec.fps, "canvas": list(spec.canvas),
                "sheetColumns": spec.sheet_columns, "seed": spec.seed, "background": "transparent",
                "renderer": "blender-native-editable-source-v48", "visualPipeline": "blender-native",
                "blendSource": "source.blend", "postRenderVisualProcessing": False,
                "profile": str(args.profile) if args.profile else None,
                "trajectoryConfig": str(args.trajectory_config) if args.trajectory_config else None,
                "trajectoryProvider": trajectory["type"] if trajectory is not None else "legacy",
                "trajectoryDimensions": trajectory.get("dimensions", 2) if trajectory is not None else 2,
            }
            write_json(output / "metadata.json", metadata)
            errors = validate_output(output)
            if errors:
                raise RuntimeError("VFX validation failed:\\n" + "\\n".join(errors))
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
            b = sub.add_parser("build", help="Build a deterministic standalone VFX sprite sheet")
            b.add_argument("--effect", choices=effect_names(), default=DEFAULT_EFFECT)
            b.add_argument("--profile", help="JSON/JSON5 effect profile/preset")
            b.add_argument("--trajectory-config", help="JSON/JSON5 2D/3D trajectory config; overrides profile trajectory")
            b.add_argument("--template")
            b.add_argument("--variant")
            b.add_argument("--frames", type=int)
            b.add_argument("--fps", type=int)
            b.add_argument("--canvas", type=parse_canvas)
            b.add_argument("--sheet-columns", type=int)
            b.add_argument("--seed", type=int)
            b.add_argument("--set", dest="set_values", action="append", default=[])
            b.add_argument("--blender", default="blender")
            b.add_argument("--output", required=True)
            b.set_defaults(func=build)
            v = sub.add_parser("validate", help="Validate generated VFX output")
            v.add_argument("output")
            v.set_defaults(func=validate)
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
        ''',
    )

    # Profiles mirror the product/effect boundaries.
    move("profiles/vfx2sheet/splash/lightning_slash.json5", "profiles/vfx2sheet/splash/lightning_slash.json5")
    move("profiles/vfx2sheet/trajectories/points_example.json5", "profiles/vfx2sheet/trajectories/points_example.json5")
    move("profiles/vfx2sheet/trajectories/conical_helix_tree.json5", "profiles/vfx2sheet/trajectories/conical_helix_tree.json5")
    old_profiles = ROOT / "profiles/vfx"
    if old_profiles.exists():
        shutil.rmtree(old_profiles)

    # Tests mirror the feature architecture. Keep Blender/output compatibility
    # gates; remove unit tests for deleted non-production PIL visual stages.
    move("tests/unit/test_vfx_spec.py", "tests/vfx2sheet/unit/test_splash_config.py")
    move("tests/unit/test_vfx_trajectory.py", "tests/vfx2sheet/unit/test_trajectory.py")
    for obsolete in (
        "tests/unit/test_vfx_dissolve.py",
        "tests/unit/test_vfx_energy_graph.py",
        "tests/unit/test_vfx_postprocess.py",
    ):
        path = ROOT / obsolete
        if path.exists():
            path.unlink()

    for name in (
        "render_saved_vfx_blend.py",
        "verify_vfx_blend_reopen.py",
        "verify_vfx_dissolve_output.py",
        "verify_vfx_legacy_baseline.py",
        "verify_vfx_output.py",
        "verify_vfx_reference.py",
        "verify_vfx_trajectory_3d_output.py",
        "verify_vfx_trajectory_output.py",
    ):
        move(f"tests/e2e/{name}", f"tests/vfx2sheet/e2e/{name}")

    move(
        "tests/vfx2sheet/fixtures/splash/lightning_slash_legacy.json",
        "tests/vfx2sheet/fixtures/splash/lightning_slash_legacy.json",
    )
    move(
        "tests/vfx2sheet/golden/splash/lightning_slash_reference.b64",
        "tests/vfx2sheet/golden/splash/lightning_slash_reference.b64",
    )
    for old_dir in (ROOT / "tests/fixtures/vfx", ROOT / "tests/golden/vfx"):
        if old_dir.exists() and not any(old_dir.iterdir()):
            old_dir.rmdir()

    replacements = {
        "motion2sheet.vfx2sheet.cli": "motion2sheet.vfx2sheet.cli",
        "motion2sheet.vfx2sheet.effects.splash.config": "motion2sheet.vfx2sheet.effects.splash.config",
        "motion2sheet.vfx2sheet.common.trajectory.config": "motion2sheet.vfx2sheet.common.trajectory.config",
        "motion2sheet.vfx2sheet.common.trajectory.blender": "motion2sheet.vfx2sheet.common.trajectory.blender",
        "profiles/vfx2sheet/splash/lightning_slash.json5": "profiles/vfx2sheet/splash/lightning_slash.json5",
        "profiles/vfx2sheet/trajectories/points_example.json5": "profiles/vfx2sheet/trajectories/points_example.json5",
        "profiles/vfx2sheet/trajectories/conical_helix_tree.json5": "profiles/vfx2sheet/trajectories/conical_helix_tree.json5",
        "tests/vfx2sheet/fixtures/splash/lightning_slash_legacy.json": "tests/vfx2sheet/fixtures/splash/lightning_slash_legacy.json",
        "tests/vfx2sheet/e2e/render_saved_vfx_blend.py": "tests/vfx2sheet/e2e/render_saved_vfx_blend.py",
        "tests/vfx2sheet/e2e/verify_vfx_blend_reopen.py": "tests/vfx2sheet/e2e/verify_vfx_blend_reopen.py",
        "tests/vfx2sheet/e2e/verify_vfx_dissolve_output.py": "tests/vfx2sheet/e2e/verify_vfx_dissolve_output.py",
        "tests/vfx2sheet/e2e/verify_vfx_legacy_baseline.py": "tests/vfx2sheet/e2e/verify_vfx_legacy_baseline.py",
        "tests/vfx2sheet/e2e/verify_vfx_output.py": "tests/vfx2sheet/e2e/verify_vfx_output.py",
        "tests/vfx2sheet/e2e/verify_vfx_reference.py": "tests/vfx2sheet/e2e/verify_vfx_reference.py",
        "tests/vfx2sheet/e2e/verify_vfx_trajectory_3d_output.py": "tests/vfx2sheet/e2e/verify_vfx_trajectory_3d_output.py",
        "tests/vfx2sheet/e2e/verify_vfx_trajectory_output.py": "tests/vfx2sheet/e2e/verify_vfx_trajectory_output.py",
        "tests/vfx2sheet/golden/splash/lightning_slash_reference.b64": "tests/vfx2sheet/golden/splash/lightning_slash_reference.b64",
    }

    # Fix references in all human-readable project files after moving.
    for path in ROOT.rglob("*"):
        if path.is_file() and ".git" not in path.parts and path.suffix in {
            ".py", ".md", ".toml", ".yml", ".yaml", ".json", ".json5"
        }:
            replace_text(path, replacements)

    # Document the stable package boundary in the feature guide.
    docs = ROOT / "docs/vfx2sheet.md"
    if docs.exists():
        content = docs.read_text(encoding="utf-8")
        marker = "## Package architecture"
        if marker not in content:
            content += textwrap.dedent('''

            ## Package architecture

            `vfx2sheet` is isolated from the motion pipeline under `motion2sheet/vfx2sheet/`.

            ```text
            motion2sheet/vfx2sheet/
            ├── cli.py
            ├── registry.py
            ├── blender_entry.py
            ├── common/
            │   ├── trajectory/
            │   └── output/
            └── effects/
                └── splash/
                    ├── effect.py
                    ├── config.py
                    └── blender/
                        └── renderer.py
            ```

            New effects belong under `effects/<effect>/`. Code is promoted to `common/`
            only after it is genuinely shared by multiple effects. The generic CLI and
            Blender bootstrap resolve effects through `registry.py`; they do not contain
            splash rendering logic.
            ''')
            docs.write_text(content, encoding="utf-8")

    print("Refactored vfx2sheet into feature/common/effects architecture")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
