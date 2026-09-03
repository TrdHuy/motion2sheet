from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from motion2sheet.motion.cli import parser
from motion2sheet.motion.model_render.profile import load_camera_profile
from motion2sheet.motion.model_render.rest import character_rest_fingerprint
from motion2sheet.motion.model_render.runner import gif_frame_durations_ms, parse_frames


def animation():
    return {"frames": [{"frame": frame} for frame in range(1, 33)]}


def _rest_rig():
    return {
        "source": {"filename": "walk.fbx", "sha256": "a" * 64},
        "coordinateSystem": {
            "space": "Blender scene after source import",
            "handedness": "right-handed",
            "rightAxis": "+X",
            "forwardAxis": "-Y",
            "upAxis": "+Z",
        },
        "units": {"system": "NONE", "metersPerBlenderUnit": 1.0},
        "restAuthority": "editGeometry",
        "editGeometrySpace": "armature-local",
        "armatureObject": {
            "name": "Armature",
            "dataName": "Armature",
            "transform": {
                "translation": [0.0, 0.0, 0.0],
                "rotationQuaternion": [1.0, 0.0, 0.0, 0.0],
                "scale": [1.0, 1.0, 1.0],
            },
        },
        "bones": [
            {
                "name": "mixamorig:Hips",
                "parent": None,
                "editGeometry": {"head": [0.0, 0.0, 1.0], "tail": [0.0, 1.0, 1.0], "roll": 0.0},
                "properties": {"useDeform": True},
            }
        ],
    }


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


def test_character_rest_fingerprint_ignores_clip_source_metadata():
    walk = _rest_rig()
    idle = copy.deepcopy(walk)
    idle["source"] = {"filename": "idle.fbx", "sha256": "b" * 64}
    idle["animation"] = {"action": "Idle", "firstFrame": 17}
    assert character_rest_fingerprint(walk) == character_rest_fingerprint(idle)


def test_character_rest_fingerprint_changes_when_rest_changes():
    first = _rest_rig()
    second = copy.deepcopy(first)
    second["bones"][0]["editGeometry"]["tail"][0] = 0.125
    assert character_rest_fingerprint(first) != character_rest_fingerprint(second)


def test_export_character_source_has_no_animation_frame_rest_sampling():
    source = (Path(__file__).parents[3] / "motion2sheet/motion/model_render/blender_export_character.py").read_text(encoding="utf-8")
    assert "bake_source_meshes_to_frame" not in source
    assert "integer_action_range" not in source
    assert "source_start" not in source
    assert "animationFrameSampled\": False" in source
    assert "capture_character_rig_document" in source
