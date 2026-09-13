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


def _write_complete_output(root: Path, slug: str, *, marker: str = "old") -> Path:
    target = root / slug
    target.mkdir(parents=True, exist_ok=True)
    (target / "animation.json").write_text(f'{{"loop": true, "marker": "{marker}"}}', encoding="utf-8")
    (target / "preview.gif").write_bytes(b"GIF89a" + marker.encode("utf-8"))
    return target


def _fake_build_clip(clip, work_root: Path, _preview_character):
    return _write_complete_output(work_root / "final", clip.slug, marker=f"new-{clip.slug}")


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


def test_existing_complete_output_is_skipped_without_expensive_setup(tmp_path: Path, monkeypatch) -> None:
    input_dir = tmp_path / "input"
    output_root = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / "Walk.fbx").write_bytes(b"walk")
    _write_complete_output(output_root, "walk")

    monkeypatch.setattr(
        MODULE,
        "_prepare_preview_character",
        lambda _root: pytest.fail("cached rerun must not prepare the preview character"),
    )

    summary = MODULE.build_reference_samples(input_dir, output_root)

    assert summary.successful == []
    assert len(summary.skipped) == 1
    assert summary.skipped[0].source.name == "Walk.fbx"
    assert "cached output already complete" in summary.skipped[0].reason
    assert summary.failed == []


def test_incomplete_existing_output_fails_with_force_hint(tmp_path: Path, monkeypatch) -> None:
    input_dir = tmp_path / "input"
    output_root = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / "Walk.fbx").write_bytes(b"walk")
    target = output_root / "walk"
    target.mkdir(parents=True)
    (target / "animation.json").write_text('{"loop": true}', encoding="utf-8")

    monkeypatch.setattr(
        MODULE,
        "_prepare_preview_character",
        lambda _root: pytest.fail("incomplete cached output must fail before expensive setup"),
    )

    summary = MODULE.build_reference_samples(input_dir, output_root)

    assert summary.successful == []
    assert summary.skipped == []
    assert len(summary.failed) == 1
    assert summary.failed[0].source.name == "Walk.fbx"
    assert "incomplete" in summary.failed[0].reason
    assert "--force" in summary.failed[0].reason


def test_force_rebuild_replaces_wrapper_outputs_and_preserves_metadata(tmp_path: Path, monkeypatch) -> None:
    input_dir = tmp_path / "input"
    output_root = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / "Walk.fbx").write_bytes(b"walk")
    target = _write_complete_output(output_root, "walk", marker="old")
    (target / "metadata.json").write_text('{"keep": true}', encoding="utf-8")

    monkeypatch.setattr(MODULE, "_prepare_preview_character", lambda _root: (Path("model"), Path("rig"), Path("skin")))
    monkeypatch.setattr(MODULE, "_build_clip", _fake_build_clip)

    summary = MODULE.build_reference_samples(input_dir, output_root, force=True)

    assert len(summary.successful) == 1
    assert summary.skipped == []
    assert summary.failed == []
    assert "new-walk" in (target / "animation.json").read_text(encoding="utf-8")
    assert (target / "preview.gif").read_bytes().endswith(b"new-walk")
    assert (target / "metadata.json").read_text(encoding="utf-8") == '{"keep": true}'


def test_batch_continues_after_one_clip_failure_and_reports_reason(tmp_path: Path, monkeypatch) -> None:
    input_dir = tmp_path / "input"
    output_root = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / "Bad.fbx").write_bytes(b"bad")
    (input_dir / "Good.fbx").write_bytes(b"good")

    monkeypatch.setattr(MODULE, "_prepare_preview_character", lambda _root: (Path("model"), Path("rig"), Path("skin")))

    def fake_build(clip, work_root, preview_character):
        if clip.path.name == "Bad.fbx":
            raise RuntimeError("normalize FBX failed: invalid rig")
        return _fake_build_clip(clip, work_root, preview_character)

    monkeypatch.setattr(MODULE, "_build_clip", fake_build)

    summary = MODULE.build_reference_samples(input_dir, output_root)

    assert [item.source.name for item in summary.successful] == ["Good.fbx"]
    assert summary.skipped == []
    assert len(summary.failed) == 1
    assert summary.failed[0].source.name == "Bad.fbx"
    assert summary.failed[0].reason == "normalize FBX failed: invalid rig"
    assert (output_root / "good" / "animation.json").is_file()
    assert not (output_root / "bad").exists()


def test_summary_prints_counts_and_failed_file_reason(capsys, tmp_path: Path) -> None:
    summary = MODULE.BuildSummary(
        successful=[MODULE.SuccessfulClip(source=tmp_path / "Good.fbx", output=tmp_path / "good")],
        skipped=[MODULE.SkippedClip(source=tmp_path / "Cached.fbx", reason="cached output already complete")],
        failed=[MODULE.FailedClip(source=tmp_path / "Bad.fbx", reason="normalize FBX failed")],
    )

    MODULE._print_summary(summary)
    output = capsys.readouterr().out

    assert "Successful: 1" in output
    assert "Skipped:    1" in output
    assert "Failed:     1" in output
    assert "PASS Good.fbx" in output
    assert "SKIP Cached.fbx: cached output already complete" in output
    assert "FAIL Bad.fbx: normalize FBX failed" in output


def test_failure_detail_prefers_runtime_error_from_command_tail() -> None:
    assert MODULE._best_failure_detail(
        [
            "Traceback (most recent call last):",
            "RuntimeError: sparse timeline rejected",
            "Error: script failed",
            "Blender quit",
        ]
    ) == "RuntimeError: sparse timeline rejected"
