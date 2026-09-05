from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from motion2sheet.motion.cli import parser
from motion2sheet.motion.model_render.profile import load_camera_profile
from motion2sheet.motion.model_render.rest import character_rest_fingerprint
from motion2sheet.motion.model_render.runner import gif_frame_durations_ms


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


def test_public_cli_keeps_export_character_without_direct_source_playback():
    root = parser()
    choices = root._subparsers._group_actions[0].choices
    export = root.parse_args(["export-character", "character.fbx", "--output", "build/character"])
    assert export.command == "export-character"
    assert "render-model-animation" not in choices
    assert "render-character-animation" not in choices


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


def test_character_rest_authority_uses_only_identity_encoding_carrier():
    source = (Path(__file__).parents[3] / "motion2sheet/motion/model_render/blender_rest_authority.py").read_text(encoding="utf-8")
    assert "M2S_CANONICAL_REST_IDENTITY_CARRIER" in source
    assert "matrix_basis = Matrix.Identity(4)" in source
    assert '"restEncodingCarrierDefinesRest": False' in source
    assert '"restEncodingSourceAnimationRead": False' in source
    assert '"restEncodingSourceAnimationSampled": False' in source


def test_motion_normalizer_rebases_motion_onto_canonical_rest_without_first_pose_rest():
    source = (Path(__file__).parents[3] / "motion2sheet/motion/model_render/blender_prepare_motion_source.py").read_text(encoding="utf-8")
    assert "build_json_scene" not in source
    assert "capture_animation_document" not in source
    assert "build_armature(canonical_rig)" in source
    assert "pose_bone.matrix = reference[frame][bone.name][\"matrixArmature\"].copy()" in source
    assert "export_action_with_static_rest_fbx(rebased_armature, rebased_action, output)" in source
    assert '"motionRebasedToCanonicalRest": True' in source
    assert '"canonicalizationOnly": True' in source
    assert '"normalizationRestDerivedFromAnimationFrame": False' in source
    assert '"staticFbxRestActionDetached": True' in source
    assert '"staticFbxRestPoseBasisIdentity": True' in source
    assert '"firstAnimationPoseUsedAsRest": False' in source
    assert '"animationFrameUsedAsRest": False' in source
    assert '"retargeting": False' in source
    assert '"fuzzyMapping": False' in source


def test_fbx_static_rest_export_detaches_action_before_export():
    source = (Path(__file__).parents[3] / "motion2sheet/motion/model_render/blender_level1.py").read_text(encoding="utf-8")
    assert "armature.animation_data.action = None" in source
    assert "pose_bone.matrix_basis = Matrix.Identity(4)" in source
    assert "bake_anim_use_all_actions=True" in source
    assert "len(bpy.data.actions) != 1" in source
