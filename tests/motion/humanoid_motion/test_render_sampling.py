from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from motion2sheet.motion.cli import parser
from motion2sheet.motion.humanoid_motion import runner
from motion2sheet.motion.humanoid_motion.runner import render_humanoid_animation, select_even_samples


def _render_cli_args() -> list[str]:
    return [
        "render-humanoid-animation",
        "--model", "model.glb",
        "--character-rig", "rig.json",
        "--skin", "skin.json",
        "--character-mapping", "mapping.json",
        "--animation", "animation.json",
        "--camera-profile", "camera.json5",
        "--output", "out",
    ]


def test_select_even_samples_20_to_8():
    selected = select_even_samples(20, 8)
    assert selected == sorted(set(selected))
    assert len(selected) == 8
    assert selected[0] == 0
    assert selected[-1] == 19
    assert selected == [0, 3, 5, 8, 11, 14, 16, 19]


def test_select_even_samples_110_to_8():
    selected = select_even_samples(110, 8)
    assert len(selected) == 8
    assert selected[0] == 0
    assert selected[-1] == 109
    assert selected == sorted(set(selected))


def test_select_even_samples_uses_all_when_requested_count_exceeds_frames():
    assert select_even_samples(4, 8) == [0, 1, 2, 3]
    assert select_even_samples(1, 8) == [0]


@pytest.mark.parametrize("sample_count", [0, -1])
def test_select_even_samples_rejects_non_positive_count(sample_count):
    with pytest.raises(ValueError, match="sample count must be positive"):
        select_even_samples(20, sample_count)


def test_cli_rejects_explicit_frames_with_sample_count():
    with pytest.raises(SystemExit):
        parser().parse_args([*_render_cli_args(), "--frames", "0,3,6", "--sample-count", "8"])


def test_python_api_rejects_explicit_frames_with_sample_count(tmp_path):
    missing = tmp_path / "missing"
    with pytest.raises(ValueError, match="mutually exclusive"):
        render_humanoid_animation(
            model_path=missing,
            character_rig_path=missing,
            skin_path=missing,
            mapping_path=missing,
            animation_path=missing,
            camera_profile_path=missing,
            output=tmp_path / "out",
            frames="all",
            sample_count=8,
        )


@pytest.mark.parametrize("output_fps", [0.0, -1.0, float("inf"), float("nan")])
def test_output_fps_must_be_positive_and_finite(tmp_path, output_fps):
    missing = tmp_path / "missing"
    with pytest.raises(ValueError, match="output FPS must be positive and finite"):
        render_humanoid_animation(
            model_path=missing,
            character_rig_path=missing,
            skin_path=missing,
            mapping_path=missing,
            animation_path=missing,
            camera_profile_path=missing,
            output=tmp_path / "out",
            output_fps=output_fps,
        )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _install_render_stubs(monkeypatch, observed_fps: list[float]) -> None:
    monkeypatch.setattr(runner, "validate_rig_document", lambda value: {"id": "character-fixture"})
    monkeypatch.setattr(runner, "validate_skin_document", lambda value, rig: value)
    monkeypatch.setattr(runner, "read_mapping", lambda path: {"id": "mapping-fixture"})
    monkeypatch.setattr(runner, "validate_character_mapping", lambda value, rig: value)
    monkeypatch.setattr(runner, "read_animation", lambda path: json.loads(path.read_text(encoding="utf-8")))
    monkeypatch.setattr(runner, "load_camera_profile", lambda path: {"id": "camera", "followRoot": False})
    monkeypatch.setattr(runner, "skin_statistics", lambda skin, rig: {"stub": True})
    monkeypatch.setattr(runner, "compose_sheet", lambda frame_paths, output, columns, canvas: {"sheetRows": 1, "sheetSize": [canvas[0] * len(frame_paths), canvas[1]]})

    def compose_gif(frame_paths, output, fps):
        observed_fps.append(fps)
        output.write_bytes(b"GIF89a")
        return {"frameDurationsMs": [125] * len(frame_paths), "totalDurationMs": 125 * len(frame_paths), "effectiveFps": fps, "quantumMs": 10}

    monkeypatch.setattr(runner, "compose_gif", compose_gif)

    def run_blender(script, blender, arguments):
        request_path = Path(arguments[arguments.index("--request") + 1])
        request = json.loads(request_path.read_text(encoding="utf-8"))
        output = Path(request["output"])
        frame_dir = output / ".frames"
        for sample in request["selectedSamples"]:
            (frame_dir / f"frame_{sample + 1:04d}.png").write_bytes(b"png")
        diagnostics = output / "diagnostics"
        payloads = {
            "model_identity": {"pass": True},
            "skin_reconstruction": {"pass": True},
            "semantic_mapping": {"pass": True},
            "retarget": {"pass": True},
            "playback": {"pass": True},
            "root_motion": {"pass": True},
            "contact": {"pass": True},
        }
        for name, payload in payloads.items():
            (diagnostics / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(runner, "_run_blender", run_blender)


def _render_fixture(tmp_path: Path) -> dict[str, Path]:
    paths = {}
    for name in ("model.glb", "rig.json", "skin.json", "mapping.json", "camera.json5"):
        path = tmp_path / name
        path.write_text("{}", encoding="utf-8")
        paths[name] = path
    animation = {
        "schema": "motion2sheet.humanoid-motion.animation",
        "id": "run",
        "canonicalSkeleton": "humanoid_v1",
        "durationSeconds": 19.0 / 30.0,
        "fps": 30.0,
        "frameCount": 20,
    }
    animation_path = tmp_path / "animation.json"
    animation_path.write_text(json.dumps(animation, sort_keys=True) + "\n", encoding="utf-8")
    paths["animation.json"] = animation_path
    return paths


def _render_with_options(tmp_path, monkeypatch, *, output_fps):
    observed_fps: list[float] = []
    _install_render_stubs(monkeypatch, observed_fps)
    paths = _render_fixture(tmp_path)
    animation_path = paths["animation.json"]
    before = _sha256(animation_path)
    report = render_humanoid_animation(
        model_path=paths["model.glb"],
        character_rig_path=paths["rig.json"],
        skin_path=paths["skin.json"],
        mapping_path=paths["mapping.json"],
        animation_path=animation_path,
        camera_profile_path=paths["camera.json5"],
        output=tmp_path / "render",
        sample_count=8,
        output_fps=output_fps,
        gif=True,
        render_samples=1,
    )
    after = _sha256(animation_path)
    return report, observed_fps, before, after


def test_output_fps_overrides_gif_presentation_only_and_preserves_animation(tmp_path, monkeypatch):
    report, observed_fps, before, after = _render_with_options(tmp_path, monkeypatch, output_fps=8.0)
    assert observed_fps == [8.0]
    assert report["fps"] == 30.0
    assert report["outputFps"] == 8.0
    assert report["renderedSamples"] == select_even_samples(20, 8)
    assert report["animationSha256Before"] == report["animationSha256After"]
    assert before == after


def test_output_fps_defaults_to_canonical_animation_fps(tmp_path, monkeypatch):
    report, observed_fps, before, after = _render_with_options(tmp_path, monkeypatch, output_fps=None)
    assert observed_fps == [30.0]
    assert report["fps"] == 30.0
    assert report["outputFps"] == 30.0
    assert before == after
