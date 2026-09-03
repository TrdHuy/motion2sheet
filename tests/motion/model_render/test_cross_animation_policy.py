from pathlib import Path


def test_cross_animation_proves_rest_families_then_deletes_fbx_before_level2_render():
    workflow = (
        Path(__file__).parents[3]
        / ".github/workflows/real-skin-cross-animation-e2e.yml"
    ).read_text(encoding="utf-8")

    family_proof = "Prove Family A and Family B rest relationships before render"
    delete = "Delete every source and normalized FBX before canonical renders"
    render = "Render SAME Family B character with Family A Walk Contract B"

    assert family_proof in workflow
    assert workflow.index(family_proof) < workflow.index(delete) < workflow.index(render)
    assert "motion2sheet export-animation-json sample/walk_mixamo.fbx" in workflow
    assert "validate_level1_rig_compatibility(rig,anchor)" in workflow
    assert "diagnose_level1_rig_compatibility(rig,character)" in workflow
    assert "validate_level2_rest_basis_eligibility(rig,character)" in workflow
    assert "l1_family['restBasisToleranceDegrees']==0.001" in workflow
    assert "level2['retargeting']['boneMapping']=='exact-name'" in workflow
    assert "level2['retargeting']['fuzzyMapping'] is False" in workflow
    assert "rm -f sample/walk_mixamo.fbx" in workflow
    assert "--compatibility-level 2" in workflow
    assert "replace incompatible animation fixture" not in workflow


def test_cross_animation_keeps_full_frame_walk_idle_run_render_and_root_motion_proof():
    workflow = (
        Path(__file__).parents[3]
        / ".github/workflows/real-skin-cross-animation-e2e.yml"
    ).read_text(encoding="utf-8")

    assert "CROSS_CANVAS: 224x224" in workflow
    assert "--canvas \"$CROSS_CANVAS\"" in workflow
    assert workflow.count("--gif --output \"$ROOT/render-") >= 3
    assert "for clip in ('walking','idle','run')" in workflow
    assert "contract_root_motion" in workflow
    assert "root_motion_difference" in workflow
    assert "gateUsesFilenameExpectation':False" in workflow
