from __future__ import annotations

import json
from pathlib import Path

import pytest

from motion2sheet.motion.cli import parser
from motion2sheet.motion.model_render import runner as runner_module


def _render_args(extra: list[str] | None = None) -> list[str]:
    return [
        "render-model-animation",
        "--model", "model.glb",
        "--character-rig", "character-rig.json",
        "--skin", "skin.json",
        "--animation-rig", "animation-rig.json",
        "--animation", "animation.json",
        "--camera-profile", "camera.json5",
        "--output", "build/render",
        *(extra or []),
    ]


def test_level2_is_explicit_opt_in_and_level1_remains_default():
    root = parser()
    direct = root.parse_args(_render_args())
    adapted = root.parse_args(_render_args(["--compatibility-level", "2"]))
    assert direct.compatibility_level == 1
    assert adapted.compatibility_level == 2


def test_level2_selection_prefers_level1_when_level1_passes(tmp_path: Path, monkeypatch):
    level1 = {
        "pass": True,
        "level": 1,
        "missingBones": [],
        "extraBones": [],
        "parentMismatches": [],
        "coordinateMismatches": [],
        "restBasisMismatchCount": 0,
        "maxRestBasisErrorDegrees": 0.0002,
        "worstRestBasisBone": "Bone",
        "restBasisToleranceDegrees": 0.001,
        "retargeting": False,
        "fuzzyMapping": False,
    }
    monkeypatch.setattr(runner_module, "diagnose_level1_rig_compatibility", lambda *_: level1)
    monkeypatch.setattr(runner_module, "validate_level1_rig_compatibility", lambda *_: level1)
    monkeypatch.setattr(
        runner_module,
        "validate_level2_rest_basis_eligibility",
        lambda *_: pytest.fail("Level-2 must not run when Level-1 passes"),
    )

    selected = runner_module._select_compatibility({}, {}, tmp_path, 2)
    assert selected["compatibilityLevel"] == 1
    assert selected["adaptationApplied"] is False
    assert selected["adaptationType"] is None


def test_level2_selection_records_explicit_exact_name_fallback(tmp_path: Path, monkeypatch):
    level1 = {
        "pass": False,
        "level": 1,
        "missingBones": [],
        "extraBones": [],
        "parentMismatches": [],
        "coordinateMismatches": [],
        "restBasisMismatchCount": 43,
        "maxRestBasisErrorDegrees": 45.245,
        "worstRestBasisBone": "mixamorig:RightHandPinky1",
        "restBasisToleranceDegrees": 0.001,
        "retargeting": False,
        "fuzzyMapping": False,
    }
    level2 = {
        "pass": True,
        "level": 2,
        "adaptationType": "rest-basis",
        "sourceRestFingerprint": "a" * 64,
        "targetRestFingerprint": "b" * 64,
        "retargeting": {"boneMapping": "exact-name", "fuzzyMapping": False},
    }
    monkeypatch.setattr(runner_module, "diagnose_level1_rig_compatibility", lambda *_: level1)
    monkeypatch.setattr(runner_module, "diagnose_level2_rest_basis_eligibility", lambda *_: level2)
    monkeypatch.setattr(runner_module, "validate_level2_rest_basis_eligibility", lambda *_: level2)

    selected = runner_module._select_compatibility({}, {}, tmp_path, 2)
    assert selected["compatibilityLevel"] == 2
    assert selected["adaptationApplied"] is True
    assert selected["adaptationType"] == "rest-basis"
    assert selected["retargeting"] == {"boneMapping": "exact-name", "fuzzyMapping": False}
    assert json.loads((tmp_path / "diagnostics" / "rig_compatibility.json").read_text()) == level1
    assert json.loads((tmp_path / "diagnostics" / "rest_basis_eligibility.json").read_text()) == level2


def test_level1_requested_still_fails_before_level2(tmp_path: Path, monkeypatch):
    level1 = {
        "pass": False,
        "level": 1,
        "missingBones": [],
        "extraBones": [],
        "parentMismatches": [],
        "coordinateMismatches": [],
        "restBasisMismatchCount": 1,
        "maxRestBasisErrorDegrees": 2.0,
        "worstRestBasisBone": "Bone",
        "restBasisToleranceDegrees": 0.001,
        "retargeting": False,
        "fuzzyMapping": False,
    }
    monkeypatch.setattr(runner_module, "diagnose_level1_rig_compatibility", lambda *_: level1)
    monkeypatch.setattr(
        runner_module,
        "validate_level1_rig_compatibility",
        lambda *_: (_ for _ in ()).throw(ValueError("Level-1 rest-basis mismatch for Bone")),
    )
    monkeypatch.setattr(
        runner_module,
        "diagnose_level2_rest_basis_eligibility",
        lambda *_: pytest.fail("Level-2 must not be consulted when maximum level is 1"),
    )

    with pytest.raises(ValueError, match="Level-1 rest-basis mismatch"):
        runner_module._select_compatibility({}, {}, tmp_path, 1)
