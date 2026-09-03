from __future__ import annotations

import json
from pathlib import Path

import pytest

from motion2sheet.motion.cli import parser
from motion2sheet.motion.model_render.profile import load_camera_profile
from motion2sheet.motion.model_render.runner import gif_frame_durations_ms, parse_frames


def animation():
    return {"frames": [{"frame": frame} for frame in range(1, 33)]}


def test_public_cli_exposes_real_model_commands():
    root = parser()
    export = root.parse_args(["export-character", "character.fbx", "--output", "build/character"])
    assert export.command == "export-character"
    render = root.parse_args([
        "render-model-animation",
        "--model", "model.glb",
        "--character-rig", "character-rig.json",
        "--skin", "skin.json",
        "--animation-rig", "animation-rig.json",
        "--animation", "animation.json",
        "--camera-profile", "camera.json5",
        "--output", "build/render",
    ])
    assert render.command == "render-model-animation"
    assert render.canvas == (320, 320)
    assert render.sheet_columns == 8


def test_parse_frames_preserves_contract_order():
    assert parse_frames("all", animation()) == list(range(1, 33))
    assert parse_frames("1,4-6,32", animation()) == [1, 4, 5, 6, 32]
    with pytest.raises(ValueError, match="outside Contract B"):
        parse_frames("33", animation())


def test_gif_timing_uses_cumulative_centisecond_quantization():
    durations = gif_frame_durations_ms(32, 30.0)
    assert len(durations) == 32
    assert set(durations) == {30, 40}
    assert sum(durations) == 1070
    assert sum(durations) != 960


def test_camera_profile_is_strict(tmp_path: Path):
    path = tmp_path / "camera.json5"
    path.write_text(json.dumps({
        "schema": "motion2sheet.camera",
        "version": 1,
        "id": "front",
        "projection": "ORTHO",
        "location": [0, -6, 1],
        "target": [0, 0, 1],
        "upAxis": [0, 0, 1],
        "orthoScale": 2.25,
        "followRoot": True,
        "margin": 1.0,
    }), encoding="utf-8")
    assert load_camera_profile(path)["id"] == "front"
    data = json.loads(path.read_text())
    data["unexpected"] = 1
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown fields"):
        load_camera_profile(path)
