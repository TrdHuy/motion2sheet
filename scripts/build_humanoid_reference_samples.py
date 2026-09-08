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
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "sample" / "humanoid_motion" / "mixamo"
MAPPING = REPO_ROOT / "profiles" / "humanoid_motion" / "mixamo_humanoid_v1.json"
CAMERA = REPO_ROOT / "profiles" / "cameras" / "front_humanoid_motion.json5"
FIXTURES = REPO_ROOT / "tests" / "motion" / "humanoid_motion" / "fixtures" / "release_assets.json"
PREPARE_MOTION_SOURCE = REPO_ROOT / "motion2sheet" / "motion" / "model_render" / "blender_prepare_motion_source.py"
OUTPUT_FILES = ("animation.json", "preview.gif")


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


@dataclass(frozen=True)
class SuccessfulClip:
    source: Path
    output: Path


@dataclass(frozen=True)
class SkippedClip:
    source: Path
    reason: str


@dataclass(frozen=True)
class FailedClip:
    source: Path
    reason: str


@dataclass
class BuildSummary:
    successful: list[SuccessfulClip] = field(default_factory=list)
    skipped: list[SkippedClip] = field(default_factory=list)
    failed: list[FailedClip] = field(default_factory=list)


class CommandFailed(RuntimeError):
    def __init__(
        self,
        step: str,
        command: list[str],
        returncode: int,
        output_tail: list[str],
    ) -> None:
        detail = _best_failure_detail(output_tail)
        message = f"{step} failed with exit code {returncode}"
        if detail:
            message += f": {detail}"
        super().__init__(message)
        self.step = step
        self.command = command
        self.returncode = returncode
        self.output_tail = output_tail


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


def _best_failure_detail(lines: list[str]) -> str:
    for marker in ("RuntimeError:", "ValueError:", "AssertionError:", "Error:"):
        for line in reversed(lines):
            if marker in line:
                return line.strip()
    return lines[-1].strip() if lines else ""


def _run(step: str, command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    process = subprocess.Popen(
        command,
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        bufsize=1,
    )
    tail: deque[str] = deque(maxlen=80)
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="", flush=True)
        stripped = line.rstrip()
        if stripped:
            tail.append(stripped)
    returncode = process.wait()
    if returncode != 0:
        raise CommandFailed(step, command, returncode, list(tail))


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
    _run(
        "preview character export",
        ["motion2sheet", "export-character", str(source), "--output", str(output)],
    )

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
    _run(
        "normalize FBX",
        [
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
        ],
    )
    _run(
        "export Source Animation JSON",
        ["motion2sheet", "export-animation-json", str(normalized), "--output", str(source_json)],
    )
    _run(
        "export Humanoid Motion",
        [
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
        ],
    )
    _run(
        "render Humanoid Motion preview",
        [
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
        ],
    )

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


def _is_complete_output(target: Path) -> bool:
    return target.is_dir() and all(
        (target / name).is_file() and (target / name).stat().st_size > 0
        for name in OUTPUT_FILES
    )


def _promote_stage(stage: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    pending: list[tuple[Path, Path]] = []
    try:
        for name in OUTPUT_FILES:
            source = stage / name
            if not source.is_file() or source.stat().st_size == 0:
                raise RuntimeError(f"staged reference output is missing or empty: {source}")
            destination = target / name
            temporary = target / f".{name}.tmp"
            shutil.copy2(source, temporary)
            pending.append((temporary, destination))
        for temporary, destination in pending:
            temporary.replace(destination)
    finally:
        for temporary, _destination in pending:
            temporary.unlink(missing_ok=True)


def _failure_reason(exc: Exception) -> str:
    message = str(exc).strip()
    return message if message else type(exc).__name__


def build_reference_samples(
    input_dir: Path,
    output_root: Path,
    *,
    force: bool = False,
) -> BuildSummary:
    clips, duplicates = discover_source_clips(input_dir)
    output_root = output_root.resolve()
    summary = BuildSummary()

    for duplicate in duplicates:
        reason = (
            f"byte-identical duplicate of {duplicate.canonical.name} "
            f"(sha256={duplicate.sha256})"
        )
        summary.skipped.append(SkippedClip(source=duplicate.skipped, reason=reason))
        print(f"SKIP {duplicate.skipped.name}: {reason}", flush=True)

    build_candidates: list[SourceClip] = []
    for clip in clips:
        target = output_root / clip.slug
        if target.exists() and not target.is_dir():
            summary.failed.append(
                FailedClip(
                    source=clip.path,
                    reason=f"output path exists but is not a directory: {target}",
                )
            )
            continue

        if target.exists() and not force:
            if _is_complete_output(target):
                reason = f"cached output already complete: {target}"
                summary.skipped.append(SkippedClip(source=clip.path, reason=reason))
                print(f"SKIP {clip.path.name}: {reason}", flush=True)
            else:
                summary.failed.append(
                    FailedClip(
                        source=clip.path,
                        reason=(
                            f"output directory exists but is incomplete: {target}; "
                            "rerun with --force to rebuild it"
                        ),
                    )
                )
            continue

        build_candidates.append(clip)

    if not build_candidates:
        return summary

    with tempfile.TemporaryDirectory(prefix="motion2sheet-reference-") as temporary:
        work_root = Path(temporary)
        try:
            preview_character = _prepare_preview_character(work_root)
        except Exception as exc:
            reason = f"shared preview character setup failed: {_failure_reason(exc)}"
            for clip in build_candidates:
                summary.failed.append(FailedClip(source=clip.path, reason=reason))
            return summary

        output_root.mkdir(parents=True, exist_ok=True)
        for clip in build_candidates:
            target = output_root / clip.slug
            print(f"\n=== Building {clip.path.name} -> {clip.slug} ===", flush=True)
            try:
                stage = _build_clip(clip, work_root, preview_character)
                _promote_stage(stage, target)
            except Exception as exc:
                reason = _failure_reason(exc)
                summary.failed.append(FailedClip(source=clip.path, reason=reason))
                print(f"FAIL {clip.path.name}: {reason}", flush=True)
                continue

            summary.successful.append(SuccessfulClip(source=clip.path, output=target))
            print(f"PASS {clip.path.name}: {target}", flush=True)

    return summary


def _print_summary(summary: BuildSummary) -> None:
    print("\n=== Humanoid reference build summary ===", flush=True)
    print(f"Successful: {len(summary.successful)}", flush=True)
    print(f"Skipped:    {len(summary.skipped)}", flush=True)
    print(f"Failed:     {len(summary.failed)}", flush=True)

    if summary.successful:
        print("\nSuccessful files:", flush=True)
        for item in summary.successful:
            print(f"  PASS {item.source.name} -> {item.output}", flush=True)

    if summary.skipped:
        print("\nSkipped files:", flush=True)
        for item in summary.skipped:
            print(f"  SKIP {item.source.name}: {item.reason}", flush=True)

    if summary.failed:
        print("\nFailed files:", flush=True)
        for item in summary.failed:
            print(f"  FAIL {item.source.name}: {item.reason}", flush=True)


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
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "rebuild clips even when animation.json + preview.gif already exist; "
            "wrapper-owned files are replaced only after a successful rebuild"
        ),
    )
    return parser


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    try:
        summary = build_reference_samples(
            args.input_folder,
            args.output_root,
            force=args.force,
        )
    except ValueError as exc:
        print("\n=== Humanoid reference build summary ===", flush=True)
        print("Successful: 0", flush=True)
        print("Skipped:    0", flush=True)
        print("Failed:     1", flush=True)
        print(f"\nInput failure: {exc}", flush=True)
        return 2

    _print_summary(summary)
    print("\nmetadata.json is intentionally not generated by this wrapper.", flush=True)
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
