from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "build_humanoid_reference_samples.py"
SPEC = importlib.util.spec_from_file_location("build_humanoid_reference_samples", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_slugify_is_stable_and_filesystem_friendly() -> None:
    assert MODULE.slugify("Sword Slash") == "sword-slash"
    assert MODULE.slugify("  Run_In Place!! ") == "run-in-place"


def test_discovery_skips_byte_identical_fbx_using_deterministic_first_filename(tmp_path: Path) -> None:
    canonical = tmp_path / "a-punch.fbx"
    duplicate = tmp_path / "z-copy.fbx"
    other = tmp_path / "run.fbx"
    canonical.write_bytes(b"same-fbx-content")
    duplicate.write_bytes(b"same-fbx-content")
    other.write_bytes(b"different-fbx-content")

    clips, duplicates = MODULE.discover_source_clips(tmp_path)

    assert [clip.path.name for clip in clips] == ["a-punch.fbx", "run.fbx"]
    assert [clip.slug for clip in clips] == ["a-punch", "run"]
    assert len(duplicates) == 1
    assert duplicates[0].skipped.name == "z-copy.fbx"
    assert duplicates[0].canonical.name == "a-punch.fbx"
    assert duplicates[0].sha256 == MODULE.sha256_file(canonical)


def test_discovery_rejects_different_content_that_collides_on_slug(tmp_path: Path) -> None:
    (tmp_path / "Punch!.fbx").write_bytes(b"first")
    (tmp_path / "Punch_.fbx").write_bytes(b"second")

    with pytest.raises(ValueError, match="different FBX files resolve to the same clip id"):
        MODULE.discover_source_clips(tmp_path)


def test_discovery_reads_only_direct_fbx_children(tmp_path: Path) -> None:
    (tmp_path / "walk.fbx").write_bytes(b"walk")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "ignored.fbx").write_bytes(b"ignored")
    (tmp_path / "ignored.txt").write_text("ignored", encoding="utf-8")

    clips, duplicates = MODULE.discover_source_clips(tmp_path)

    assert [clip.path.name for clip in clips] == ["walk.fbx"]
    assert duplicates == []


def test_discovery_rejects_empty_folder(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="contains no FBX files"):
        MODULE.discover_source_clips(tmp_path)
