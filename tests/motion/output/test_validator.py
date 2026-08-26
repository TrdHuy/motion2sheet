from motion2sheet.motion.common.model import CANONICAL_JOINTS, PoseFrame, PoseSequence
from motion2sheet.motion.output import validate_sequence


def dynamic_frame(offset: float = 0.0):
    joints = {name: (50.0, 50.0) for name in CANONICAL_JOINTS}
    joints["head"] = (50.0, 15.0)
    joints["neck"] = (50.0, 25.0)
    joints["pelvis"] = (50.0, 55.0)
    joints["left_wrist"] = (30.0 + offset, 45.0)
    joints["right_wrist"] = (70.0 - offset, 45.0)
    joints["left_knee"] = (44.0 + offset * 0.4, 70.0)
    joints["right_knee"] = (56.0 - offset * 0.4, 70.0)
    joints["left_ankle"] = (42.0 + offset * 0.5, 92.0)
    joints["right_ankle"] = (58.0 - offset * 0.5, 92.0)
    return PoseFrame(joints)


def test_validator_accepts_valid_sequence():
    sequence = PoseSequence(
        "walk", "down", (100, 100), (50, 84),
        [dynamic_frame(0.0), dynamic_frame(4.0), dynamic_frame(-4.0)],
    )
    assert validate_sequence(sequence, expected_frames=3) == []


def test_validator_reports_missing_joint():
    joints = dynamic_frame().joints.copy()
    del joints["head"]
    sequence = PoseSequence("walk", "down", (100, 100), (50, 84), [PoseFrame(joints)])
    errors = validate_sequence(sequence, expected_frames=1)
    assert any("missing joints: head" in error for error in errors)


def test_validator_rejects_static_animation():
    frame = dynamic_frame(0.0)
    sequence = PoseSequence("walk", "down", (100, 100), (50, 84), [frame, frame, frame])
    errors = validate_sequence(sequence, expected_frames=3)
    assert any("animation appears static" in error for error in errors)


def test_validator_rejects_collapsed_projection():
    joints = {name: (50.0, 50.0) for name in CANONICAL_JOINTS}
    joints["head"] = (50.0, 44.0)
    joints["pelvis"] = (50.0, 50.0)
    joints["left_wrist"] = (48.0, 49.0)
    joints["right_wrist"] = (52.0, 49.0)
    joints["left_ankle"] = (49.0, 56.0)
    joints["right_ankle"] = (51.0, 56.0)
    sequence = PoseSequence("walk", "down", (100, 100), (50, 84), [PoseFrame(joints)])
    errors = validate_sequence(sequence, expected_frames=1)
    assert any("projected skeleton is too short" in error for error in errors)
