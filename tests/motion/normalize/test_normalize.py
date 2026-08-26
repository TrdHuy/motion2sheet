from motion2sheet.motion.normalize import normalize_projected_sequences


def frame(offset=0.0):
    return {
        "head": (0.0, 2.0 + offset),
        "neck": (0.0, 1.7 + offset),
        "left_shoulder": (-0.3, 1.6 + offset),
        "left_elbow": (-0.5, 1.2 + offset),
        "left_wrist": (-0.6, 0.8 + offset),
        "right_shoulder": (0.3, 1.6 + offset),
        "right_elbow": (0.5, 1.2 + offset),
        "right_wrist": (0.6, 0.8 + offset),
        "pelvis": (0.0, 1.0 + offset),
        "left_hip": (-0.2, 1.0 + offset),
        "left_knee": (-0.2, 0.5 + offset),
        "left_ankle": (-0.2, 0.0 + offset),
        "right_hip": (0.2, 1.0 + offset),
        "right_knee": (0.2, 0.5 + offset),
        "right_ankle": (0.2, 0.0 + offset),
    }


def test_normalization_uses_common_canvas_and_anchor():
    result = normalize_projected_sequences(
        {"down": [frame(0.0), frame(0.1)], "left": [frame(0.2), frame(0.3)]},
        action="walk",
        canvas=(320, 320),
    )
    assert result["down"].canvas == (320, 320)
    assert result["left"].anchor == result["down"].anchor
    for sequence in result.values():
        for pose in sequence.frames:
            for x, y in pose.joints.values():
                assert 0 <= x < 320
                assert 0 <= y < 320
