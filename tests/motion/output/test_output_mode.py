import json
from pathlib import Path

from PIL import Image

from motion2sheet.motion.cli import parser
from motion2sheet.motion.common.model import CANONICAL_JOINTS, PoseFrame, PoseSequence
from motion2sheet.motion.output import DEFAULT_OUTPUT_MODE, validate_output_directory


def _frame(offset: float) -> PoseFrame:
    joints = {name: (50.0, 50.0) for name in CANONICAL_JOINTS}
    joints.update(
        {
            "head": (50.0, 15.0),
            "neck": (50.0, 25.0),
            "pelvis": (50.0, 55.0),
            "left_wrist": (30.0 + offset, 45.0),
            "right_wrist": (70.0 - offset, 45.0),
            "left_knee": (44.0 + offset * 0.4, 70.0),
            "right_knee": (56.0 - offset * 0.4, 70.0),
            "left_ankle": (42.0 + offset * 0.5, 92.0),
            "right_ankle": (58.0 - offset * 0.5, 92.0),
        }
    )
    return PoseFrame(joints)


def _make_output(root: Path, mode: str, *, write_output_mode: bool = True) -> None:
    direction = root / "down"
    direction.mkdir(parents=True)
    sequence = PoseSequence(
        "walk",
        "down",
        (100, 100),
        (50, 84),
        [_frame(0.0), _frame(4.0), _frame(-4.0)],
    )
    (direction / "pose.json").write_text(json.dumps(sequence.to_dict()), encoding="utf-8")
    metadata = {
        "frames": 3,
        "canvas": [100, 100],
        "sheetColumns": 2,
        "directions": ["down"],
    }
    if write_output_mode:
        metadata["outputMode"] = mode
    (root / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    if mode in ("both", "frames"):
        frames = direction / "frames"
        frames.mkdir()
        for index in range(1, 4):
            Image.new("RGBA", (100, 100)).save(frames / f"{index:02d}.png")
    if mode in ("both", "sheet"):
        Image.new("RGBA", (200, 200)).save(direction / "pose_sheet.png")


def test_cli_defaults_to_both_output_mode():
    args = parser().parse_args(["build", "walk.fbx", "--output", "build/walk"])
    assert args.output_mode == DEFAULT_OUTPUT_MODE == "both"


def test_cli_accepts_all_output_modes():
    for mode in ("both", "frames", "sheet"):
        args = parser().parse_args(
            ["build", "walk.fbx", "--output", "build/walk", "--output-mode", mode]
        )
        assert args.output_mode == mode


def test_validator_accepts_both_mode(tmp_path):
    _make_output(tmp_path, "both")
    assert validate_output_directory(tmp_path) == []


def test_validator_accepts_frames_mode(tmp_path):
    _make_output(tmp_path, "frames")
    assert validate_output_directory(tmp_path) == []


def test_validator_accepts_sheet_mode(tmp_path):
    _make_output(tmp_path, "sheet")
    assert validate_output_directory(tmp_path) == []


def test_legacy_metadata_without_output_mode_defaults_to_both(tmp_path):
    _make_output(tmp_path, "both", write_output_mode=False)
    assert validate_output_directory(tmp_path) == []


def test_validator_rejects_unknown_output_mode(tmp_path):
    _make_output(tmp_path, "both")
    metadata_path = tmp_path / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["outputMode"] = "unknown"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    assert validate_output_directory(tmp_path) == ["unsupported outputMode: unknown"]


def test_validator_rejects_sheet_in_frames_mode(tmp_path):
    _make_output(tmp_path, "frames")
    Image.new("RGBA", (200, 200)).save(tmp_path / "down" / "pose_sheet.png")
    errors = validate_output_directory(tmp_path)
    assert any("must not exist in outputMode=frames" in error for error in errors)


def test_validator_rejects_frames_directory_in_sheet_mode(tmp_path):
    _make_output(tmp_path, "sheet")
    frames = tmp_path / "down" / "frames"
    frames.mkdir()
    errors = validate_output_directory(tmp_path)
    assert any("frames directory must not exist in outputMode=sheet" in error for error in errors)
