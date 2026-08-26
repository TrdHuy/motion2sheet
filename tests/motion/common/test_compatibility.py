def test_legacy_motion_facades_resolve_to_canonical_implementations():
    from motion2sheet.cli import main as legacy_main
    from motion2sheet.model import PoseFrame as legacy_pose_frame
    from motion2sheet.normalize import normalize_projected_sequences as legacy_normalize
    from motion2sheet.renderer import render_sequence as legacy_render
    from motion2sheet.retarget import retarget_frames as legacy_retarget
    from motion2sheet.validator import validate_sequence as legacy_validate

    from motion2sheet.motion.cli import main
    from motion2sheet.motion.common.model import PoseFrame
    from motion2sheet.motion.normalize import normalize_projected_sequences
    from motion2sheet.motion.output import validate_sequence
    from motion2sheet.motion.render import render_sequence
    from motion2sheet.motion.retarget import retarget_frames

    assert legacy_main is main
    assert legacy_pose_frame is PoseFrame
    assert legacy_normalize is normalize_projected_sequences
    assert legacy_render is render_sequence
    assert legacy_retarget is retarget_frames
    assert legacy_validate is validate_sequence
