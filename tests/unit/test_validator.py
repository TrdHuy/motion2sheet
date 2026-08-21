from motion2sheet.model import CANONICAL_JOINTS, PoseFrame, PoseSequence
from motion2sheet.validator import validate_sequence


def test_validator_accepts_valid_sequence():
    joints = {name: (50.0, 50.0) for name in CANONICAL_JOINTS}
    sequence = PoseSequence("walk", "down", (100, 100), (50, 84), [PoseFrame(joints)] * 8)
    assert validate_sequence(sequence, expected_frames=8) == []


def test_validator_reports_missing_joint():
    joints = {name: (50.0, 50.0) for name in CANONICAL_JOINTS if name != "head"}
    sequence = PoseSequence("walk", "down", (100, 100), (50, 84), [PoseFrame(joints)])
    errors = validate_sequence(sequence, expected_frames=1)
    assert any("missing joints: head" in error for error in errors)
