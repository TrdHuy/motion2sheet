from PIL import Image, ImageDraw

from motion2sheet.motion.roundtrip.visual import MIN_CELL_CONTENT_PIXELS, sheet_layout_metrics
from motion2sheet.motion.roundtrip.visual_contract import PANEL, panel_box, sheet_size


def _sheet_with_content(
    frame_count: int,
    occupied_indices: set[int],
    background: tuple[int, int, int] = (255, 255, 255),
) -> Image.Image:
    sheet = Image.new("RGB", sheet_size(frame_count), background)
    draw = ImageDraw.Draw(sheet)
    for index in occupied_indices:
        left, top, _right, _bottom = panel_box(index)
        # A small dark block is enough to model skeleton foreground while staying
        # well above the production gate's minimum occupancy requirement.
        side = max(5, int(MIN_CELL_CONTENT_PIXELS**0.5) + 1)
        draw.rectangle((left + 20, top + 20, left + 20 + side, top + 20 + side), fill=(20, 20, 20))
    return sheet


def test_layout_gate_requires_content_in_every_expected_cell():
    frames = tuple(range(1, 33))
    metrics = sheet_layout_metrics(_sheet_with_content(32, set(range(32))), frames)

    assert metrics["pass"] is True
    assert metrics["expectedCells"] == 32
    assert metrics["occupiedCells"] == 32
    assert metrics["emptyCells"] == []
    assert metrics["minContentPixels"] >= MIN_CELL_CONTENT_PIXELS


def test_layout_gate_treats_evee_gray_background_as_background_not_content():
    frames = tuple(range(1, 33))
    # Blender's color-managed flat background is around luma 196-197 in the
    # real proof artifact rather than literal RGB white.
    metrics = sheet_layout_metrics(_sheet_with_content(32, set(), background=(197, 197, 197)), frames)

    assert metrics["pass"] is False
    assert metrics["occupiedCells"] == 0
    assert len(metrics["emptyCells"]) == 32
    assert metrics["minContentPixels"] == 0
    assert metrics["minBackgroundLuma"] == 197


def test_layout_gate_rejects_matching_camera_crop_even_when_center_cells_have_content():
    frames = tuple(range(1, 33))
    # Reproduce the old camera failure shape: only a centered 4x2 region of the
    # expected 8x4 sheet contains skeleton pixels, on the real Eevee-like gray
    # background rather than an ideal white one.
    centered_four_by_two = {
        row * 8 + column
        for row in (1, 2)
        for column in (2, 3, 4, 5)
    }
    metrics = sheet_layout_metrics(
        _sheet_with_content(32, centered_four_by_two, background=(197, 197, 197)),
        frames,
    )

    assert metrics["pass"] is False
    assert metrics["expectedCells"] == 32
    assert metrics["occupiedCells"] == 8
    assert len(metrics["emptyCells"]) == 24
    assert {cell["index"] for cell in metrics["emptyCells"]}.isdisjoint(centered_four_by_two)


def test_layout_gate_reports_specific_missing_frame_and_preserves_8x4_geometry():
    frames = tuple(range(1, 33))
    occupied = set(range(32)) - {31}
    metrics = sheet_layout_metrics(_sheet_with_content(32, occupied), frames)

    assert sheet_size(32) == (8 * PANEL, 4 * PANEL)
    assert metrics["pass"] is False
    assert metrics["occupiedCells"] == 31
    assert metrics["emptyCells"] == [{"index": 31, "frame": 32}]
