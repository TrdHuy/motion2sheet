#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import unicodedata
import urllib.request
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "sample" / "humanoid_motion" / "mixamo"
MAPPING = REPO_ROOT / "profiles" / "humanoid_motion" / "mixamo_humanoid_v1.json"
CAMERA = REPO_ROOT / "profiles" / "cameras" / "front_humanoid_motion.json5"
FIXTURES = REPO_ROOT / "tests" / "motion" / "humanoid_motion" / "fixtures" / "release_assets.json"
PREPARE_MOTION_SOURCE = REPO_ROOT / "motion2sheet" / "motion" / "model_render" / "blender_prepare_motion_source.py"


@dataclass(frozen=True)
class SourceClip:
    path: Path
    slug: str
    sha256: str


@dataclass(frozen=True)
class DuplicateClip:
    skipped: Path
    canonical: Path
    sha256: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def slugify(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    if not slug:
        raise ValueError(f"cannot derive a clip id from filename stem: {name!r}")
    return slug


def discover_source_clips(input_dir: Path) -> tuple[list[SourceClip], list[DuplicateClip]]:
    input_dir = input_dir.resolve()
    if not input_dir.is_dir():
        raise ValueError(f"input folder does not exist: {input_dir}")

    files = sorted(
        (path for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() == ".fbx"),
        key=lambda path: (path.name.casefold(), path.name),
    )
    if not files:
        raise ValueError(f"input folder contains no FBX files: {input_dir}")

    first_by_hash: dict[str, Path] = {}
    selected: list[SourceClip] = []
    duplicates: list[DuplicateClip] = []
    for path in files:
        digest = sha256_file(path)
        canonical = first_by_hash.get(digest)
        if canonical is not None:
            duplicates.append(DuplicateClip(skipped=path, canonical=canonical, sha256=digest))
            continue
        first_by_hash[digest] = path
        selected.append(SourceClip(path=path, slug=slugify(path.stem), sha256=digest))

    by_slug: dict[str, SourceClip] = {}
    for clip in selected:
        previous = by_slug.get(clip.slug)
        if previous is not None:
            raise ValueError(
                "different FBX files resolve to the same clip id "
                f"{clip.slug!r}: {previous.path.name!r} ({previous.sha256}) vs "
                f"{clip.path.name!r} ({clip.sha256})"
            )
        by_slug[clip.slug] = clip

    return selected, duplicates


def _run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=REPO_ROOT, check=True)


def _download_preview_character(destination: Path) -> None:
    manifest = json.loads(FIXTURES.read_text(encoding="utf-8"))
    asset = manifest["assets"]["character-a"]
    expected_sha = asset["sha256"]
    expected_size = int(asset["size"])
    url = asset["url"]

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".download")
    request = urllib.request.Request(url, headers={"User-Agent": "motion2sheet-reference-wrapper"})
    with urllib.request.urlopen(request) as response, temporary.open("wb") as handle:
        shutil.copyfileobj(response, handle)

    actual_size = temporary.stat().st_size
    actual_sha = sha256_file(temporary)
    if actual_size != expected_size or actual_sha != expected_sha:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(
            "pinned preview character verification failed: "
            f"size={actual_size}/{expected_size} sha256={actual_sha}/{expected_sha}"
        )
    temporary.replace(destination)


def _prepare_preview_character(work_root: Path) -> tuple[Path, Path, Path]:
    source = work_root / "preview-character" / "character-a.fbx"
    output = work_root / "preview-character" / "export"
    _download_preview_character(source)
    _run(["motion2sheet", "export-character", str(source), "--output", str(output)])

    model = output / "model.glb"
    rig = output / "rig.json"
    skin = output / "skin.json"
    for path in (model, rig, skin):
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"preview character export missing output: {path}")
    return model, rig, skin


def _build_clip(clip: SourceClip, work_root: Path, preview_character: tuple[Path, Path, Path]) -> Path:
    clip_root = work_root / "clips" / clip.slug
    normalized = clip_root / "normalized.fbx"
    normalization_report = clip_root / "normalization.json"
    source_json = clip_root / "source-json"
    humanoid = clip_root / "humanoid"
    render = clip_root / "render"
    final = work_root / "final" / clip.slug
    model, rig, skin = preview_character

    clip_root.mkdir(parents=True, exist_ok=True)
    _run([
        "blender",
        "--background",
        "--factory-startup",
        "--python-exit-code",
        "1",
        "--python",
        str(PREPARE_MOTION_SOURCE),
        "--",
        "--input",
        str(clip.path),
        "--output",
        str(normalized),
        "--report",
        str(normalization_report),
    ])
    _run(["motion2sheet", "export-animation-json", str(normalized), "--output", str(source_json)])
    _run([
        "motion2sheet",
        "export-humanoid-animation",
        "--source-rig",
        str(source_json / "rig.json"),
        "--source-animation",
        str(source_json / "animation.json"),
        "--mapping",
        str(MAPPING),
        "--id",
        clip.slug,
        "--loop",
        "--output",
        str(humanoid),
    ])
    _run([
        "motion2sheet",
        "render-humanoid-animation",
        "--model",
        str(model),
        "--character-rig",
        str(rig),
        "--skin",
        str(skin),
        "--character-mapping",
        str(MAPPING),
        "--animation",
        str(humanoid / "animation.json"),
        "--camera-profile",
        str(CAMERA),
        "--canvas",
        "224x224",
        "--sheet-columns",
        "8",
        "--render-samples",
        "1",
        "--gif",
        "--output",
        str(render),
    ])

    animation = humanoid / "animation.json"
    preview = render / "preview.gif"
    for path in (animation, preview):
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"reference sample build missing output: {path}")

    document = json.loads(animation.read_text(encoding="utf-8"))
    if document.get("loop") is not True:
        raise RuntimeError(f"reference animation must be looped: {animation}")

    final.mkdir(parents=True, exist_ok=False)
    shutil.copy2(animation, final / "animation.json")
    shutil.copy2(preview, final / "preview.gif")
    return final


def build_reference_samples(input_dir: Path, output_root: Path) -> list[Path]:
    clips, duplicates = discover_source_clips(input_dir)
    output_root = output_root.resolve()

    for duplicate in duplicates:
        print(
            "Duplicate FBX skipped: "
            f"{duplicate.skipped.name} -> {duplicate.canonical.name} "
            f"sha256={duplicate.sha256}",
            flush=True,
        )

    conflicts = [output_root / clip.slug for clip in clips if (output_root / clip.slug).exists()]
    if conflicts:
        joined = ", ".join(str(path) for path in conflicts)
        raise ValueError(f"reference output already exists; refusing to overwrite trusted sample: {joined}")

    with tempfile.TemporaryDirectory(prefix="motion2sheet-reference-") as temporary:
        work_root = Path(temporary)
        preview_character = _prepare_preview_character(work_root)
        staged = [_build_clip(clip, work_root, preview_character) for clip in clips]

        output_root.mkdir(parents=True, exist_ok=True)
        promoted: list[Path] = []
        for stage in staged:
            target = output_root / stage.name
            shutil.copytree(stage, target)
            promoted.append(target)

    return promoted


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a flat folder of trusted Mixamo FBX animations into Humanoid Motion "
            "reference samples containing animation.json + preview.gif. All exported references loop."
        )
    )
    parser.add_argument("input_folder", type=Path, help="folder whose direct children are animation FBX files")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help=f"reference output root (default: {DEFAULT_OUTPUT_ROOT.relative_to(REPO_ROOT)})",
    )
    return parser


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    try:
        promoted = build_reference_samples(args.input_folder, args.output_root)
    except ValueError as exc:
        parser.error(str(exc))

    print(f"Built {len(promoted)} trusted Humanoid Motion reference sample(s):", flush=True)
    for path in promoted:
        print(f"  {path}", flush=True)
    print("metadata.json is intentionally not generated by this wrapper.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
