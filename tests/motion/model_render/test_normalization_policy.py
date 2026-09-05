from pathlib import Path


def test_normalization_keeps_semantic_level1_separate_from_fbx_serialization_noise():
    source = (
        Path(__file__).parents[3]
        / "motion2sheet/motion/model_render/blender_prepare_motion_source.py"
    ).read_text(encoding="utf-8")

    assert "CANONICAL_REBASE_TRANSLATION_TOLERANCE = 1e-5" in source
    assert "CANONICAL_REBASE_HEAD_TAIL_TOLERANCE = 1e-5" in source
    assert "FBX_SERIALIZATION_TRANSLATION_TOLERANCE = 2e-5" in source
    assert "FBX_SERIALIZATION_HEAD_TAIL_TOLERANCE = 2e-5" in source
    assert '"level1RestBasisToleranceChanged": False' in source
    assert "validate_level1_rig_compatibility(normalized_rig, canonical_source_rig)" in source
    assert 'phase="canonical-rest-rebase-before-fbx"' in source
    assert 'phase="after-fbx-serialization-and-import"' in source
