from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
from pathlib import Path
from typing import Iterable

DEFAULT_MANIFEST = Path(__file__).with_name("components.json")
DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
ANIMATION_ROOT = Path("profiles/anim2sheet/animations")
ANIMATION_TEST_ROOT = Path("tests/anim2sheet/animations")
REQUIRED_ANIMATION_FILES = ("animation.json5", "pose_reference.json", "joint_contract.json")
SAFE_CLIP_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def matches(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def animation_target_prefix(clip: str) -> str:
    return f"anim-{clip.replace('_', '-')}"


def discover_animation_clips(repo_root: Path = DEFAULT_REPO_ROOT) -> list[str]:
    animation_root = repo_root / ANIMATION_ROOT
    if not animation_root.is_dir():
        return []
    clips: list[str] = []
    target_prefixes: set[str] = set()
    for candidate in sorted(animation_root.iterdir(), key=lambda path: path.name):
        if not candidate.is_dir():
            continue
        if not all((candidate / filename).is_file() for filename in REQUIRED_ANIMATION_FILES):
            continue
        clip = candidate.name
        if not SAFE_CLIP_NAME.fullmatch(clip):
            raise ValueError(f"Invalid animation clip directory name: {clip!r}")
        prefix = animation_target_prefix(clip)
        if prefix in target_prefixes:
            raise ValueError(f"Animation clip CI target collision for {clip!r}: {prefix!r}")
        target_prefixes.add(prefix)
        clips.append(clip)
    return clips


def add_discovered_animation_targets(manifest: dict, repo_root: Path = DEFAULT_REPO_ROOT) -> dict:
    targets = manifest["test_targets"]
    for clip in discover_animation_clips(repo_root):
        prefix = animation_target_prefix(clip)
        profile_paths = [f"{ANIMATION_ROOT.as_posix()}/{clip}/**"]
        unit_dir = repo_root / ANIMATION_TEST_ROOT / clip / "unit"
        if unit_dir.is_dir():
            targets[f"{prefix}-unit"] = {
                "kind": "unit",
                "path": f"{ANIMATION_TEST_ROOT.as_posix()}/{clip}/unit",
                "paths": [*profile_paths, f"{ANIMATION_TEST_ROOT.as_posix()}/{clip}/unit/**"],
                "depends_on": ["anim-core"],
            }
        targets[f"{prefix}-e2e"] = {
            "kind": "anim-e2e",
            "target": clip,
            "paths": [
                *profile_paths,
                f"{ANIMATION_TEST_ROOT.as_posix()}/{clip}/e2e/**",
                "tests/anim2sheet/common/authority/**",
            ],
            "depends_on": ["anim-core"],
        }
    return manifest


def load_manifest(path: Path = DEFAULT_MANIFEST, *, repo_root: Path = DEFAULT_REPO_ROOT) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    return add_discovered_animation_targets(manifest, repo_root)


def changed_files(base: str, head: str) -> list[str]:
    result = subprocess.run(["git", "diff", "--name-only", base, head], check=True, text=True, capture_output=True)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def component_closure(manifest: dict, direct: set[str]) -> set[str]:
    components = manifest["components"]
    affected = set(direct)
    changed = True
    while changed:
        changed = False
        for name, config in components.items():
            if name in affected:
                continue
            if any(dependency in affected for dependency in config.get("depends_on", [])):
                affected.add(name)
                changed = True
    return affected


def resolve_targets(manifest: dict, paths: list[str], *, full: bool = False) -> tuple[set[str], set[str]]:
    targets = manifest["test_targets"]
    if full:
        return set(manifest["components"]), set(targets)
    global_paths = manifest.get("global_paths", [])
    ignore_paths = manifest.get("ignore_paths", [])
    components = manifest["components"]
    if any(matches(path, global_paths) for path in paths):
        return set(components), set(targets)
    direct_components = {
        name for name, config in components.items()
        if any(matches(path, config.get("paths", [])) for path in paths)
    }
    affected_components = component_closure(manifest, direct_components)
    affected_targets: set[str] = set()
    matched_paths: set[str] = set()
    for path in paths:
        if matches(path, ignore_paths) or matches(path, global_paths):
            matched_paths.add(path)
        for config in components.values():
            if matches(path, config.get("paths", [])):
                matched_paths.add(path)
        for name, config in targets.items():
            if matches(path, config.get("paths", [])):
                affected_targets.add(name)
                matched_paths.add(path)
    for name, config in targets.items():
        if any(dependency in affected_components for dependency in config.get("depends_on", [])):
            affected_targets.add(name)
    unmatched = [path for path in paths if path not in matched_paths]
    if unmatched:
        return set(components), set(targets)
    return affected_components, affected_targets


def matrix_for(manifest: dict, target_names: set[str], kind: str) -> dict:
    include = []
    for name in sorted(target_names):
        config = manifest["test_targets"][name]
        if config["kind"] != kind:
            continue
        item = {"name": name}
        if "path" in config:
            item["path"] = config["path"]
        if "target" in config:
            item["target"] = config["target"]
        include.append(item)
    return {"include": include}


def emit_outputs(manifest: dict, target_names: set[str], affected_components: set[str]) -> None:
    groups = {
        "unit": matrix_for(manifest, target_names, "unit"),
        "motion_e2e": matrix_for(manifest, target_names, "motion-e2e"),
        "vfx_e2e": matrix_for(manifest, target_names, "vfx-e2e"),
        "anim_e2e": matrix_for(manifest, target_names, "anim-e2e"),
    }
    for key, matrix in groups.items():
        print(f"{key}_matrix={json.dumps(matrix, separators=(',', ':'))}")
        print(f"{key}_count={len(matrix['include'])}")
    print(f"affected_components={json.dumps(sorted(affected_components), separators=(',', ':'))}")
    print(f"affected_targets={json.dumps(sorted(target_names), separators=(',', ':'))}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    result.add_argument("--base")
    result.add_argument("--head")
    result.add_argument("--full", action="store_true")
    result.add_argument("--files", nargs="*")
    return result


def main() -> int:
    args = parser().parse_args()
    manifest = load_manifest(args.manifest)
    if args.full:
        paths: list[str] = []
    elif args.files is not None:
        paths = args.files
    else:
        if not args.base or not args.head:
            raise SystemExit("--base and --head are required unless --full or --files is used")
        paths = changed_files(args.base, args.head)
    components, targets = resolve_targets(manifest, paths, full=args.full)
    emit_outputs(manifest, targets, components)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
