from pathlib import Path


def test_cross_animation_fails_closed_before_any_fixed_character_render():
    workflow = (
        Path(__file__).parents[3]
        / ".github/workflows/real-skin-cross-animation-e2e.yml"
    ).read_text(encoding="utf-8")

    preflight = "Fail closed unless every Source Rig matches fixed character Level-1"
    delete = "Delete every FBX before canonical JSON-only renders"
    render = "Render SAME character with Walking Source Animation"

    assert preflight in workflow
    assert workflow.index(preflight) < workflow.index(delete) < workflow.index(render)
    assert "diagnose_level1_rig_compatibility(rig,character)" in workflow
    assert "validate_level1_rig_compatibility(rig,character)" in workflow
    assert "restBasisMismatchCount" in workflow
    assert "maxRestBasisErrorDegrees" in workflow
    assert "worstRestBasisBone" in workflow
    assert "restBasisToleranceDegrees':0.001" in workflow
    assert "retargetingPermitted':False" in workflow
    assert "fuzzyMappingPermitted':False" in workflow
    assert "replace incompatible animation fixture(s), do not retarget" in workflow


def test_cross_animation_keeps_full_frame_render_but_uses_proof_resolution():
    workflow = (
        Path(__file__).parents[3]
        / ".github/workflows/real-skin-cross-animation-e2e.yml"
    ).read_text(encoding="utf-8")

    assert "CROSS_CANVAS: 224x224" in workflow
    assert "--canvas \"$CROSS_CANVAS\"" in workflow
    assert "--gif" in workflow
    assert "for clip in ('walking','idle','run')" in workflow
