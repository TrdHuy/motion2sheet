from pathlib import Path

from PIL import Image

from motion2sheet.motion.common.model import PoseFrame, PoseSequence
from motion2sheet.motion.render import compose_sheet, render_sequence


def sample_frame():
    joints = {
        "head": (50, 20), "neck": (50, 35),
        "left_shoulder": (40, 40), "left_elbow": (30, 55), "left_wrist": (25, 70),
        "right_shoulder": (60, 40), "right_elbow": (70, 55), "right_wrist": (75, 70),
        "pelvis": (50, 65),
        "left_hip": (45, 68), "left_knee": (42, 82), "left_ankle": (40, 95),
        "right_hip": (55, 68), "right_knee": (58, 82), "right_ankle": (60, 95),
    }
    return PoseFrame(joints)


def test_render_and_sheet(tmp_path: Path):
    sequence = PoseSequence("walk", "down", (100, 100), (50, 84), [sample_frame()] * 8)
    frames = render_sequence(sequence, tmp_path / "frames")
    sheet_path = compose_sheet(frames, tmp_path / "sheet.png", columns=4)
    assert len(frames) == 8
    with Image.open(sheet_path) as image:
        assert image.size == (400, 200)
