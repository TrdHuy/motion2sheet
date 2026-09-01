import pytest

from motion2sheet.motion.roundtrip.visual_contract import (
    COLUMNS,
    PANEL,
    PADDING,
    frame_numbers,
    panel_box,
    panel_pixel,
    panel_origin,
    project_point,
    projection_config,
    sheet_pixel,
    sheet_size,
)


def pose_data():
    source_frame = {
        "Bone": {
            "head": [0.0, 0.0, 0.0],
            "tail": [1.0, 0.0, 1.0],
        }
    }
    reconstructed_frame = {
        "Bone": {
            "head": [0.0, 0.0, 0.0],
            "tail": [1.0, 0.0, 1.0],
        }
    }
    return {
        "frameRange": [1, 2],
        "source": {"1": source_frame, "2": source_frame},
        "reconstructed": {"1": reconstructed_frame, "2": reconstructed_frame},
    }


def test_projection_formula_is_canonical():
    assert project_point([1.0, 2.0, 3.0]) == pytest.approx((0.16, 3.4))


def test_projection_config_and_pixel_mapping_are_deterministic():
    data = pose_data()
    config = projection_config(data)
    assert panel_pixel([0.0, 0.0, 0.0], config) == (18, 238)
    assert panel_pixel([1.0, 0.0, 1.0], config) == (238, 18)


def test_sheet_layout_is_owned_by_shared_contract():
    assert PANEL == 256
    assert PADDING == 18
    assert COLUMNS == 8
    assert sheet_size(1) == (2048, 256)
    assert sheet_size(9) == (2048, 512)
    assert panel_origin(8) == (0, 256)
    assert panel_box(8) == (0, 256, 256, 512)


def test_sheet_pixel_adds_panel_offset_after_canonical_pixel_snap():
    config = projection_config(pose_data())
    assert sheet_pixel(8, [0.0, 0.0, 0.0], config) == (18, 494)


def test_frame_numbers_are_inclusive_and_fail_closed_for_empty_range():
    assert frame_numbers(pose_data()) == (1, 2)
    with pytest.raises(ValueError, match="no frames"):
        frame_numbers({"frameRange": [2, 1]})


def test_sheet_layout_rejects_invalid_inputs():
    with pytest.raises(ValueError, match="positive"):
        sheet_size(0)
    with pytest.raises(ValueError, match="non-negative"):
        panel_origin(-1)
