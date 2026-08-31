from __future__ import annotations

from pathlib import Path

from PIL import Image

from motion2sheet.anim2sheet.common.output.packer import write_camera_previews


def _write_frame(path: Path, color: tuple[int, int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    image.putpixel((2, 2), color)
    image.save(path)
    image.close()


def _prepare_frames(root: Path, cameras: list[str], frames: list[int]) -> dict[Path, bytes]:
    colors = [
        (255, 0, 0, 255),
        (0, 255, 0, 255),
        (0, 0, 255, 255),
    ]
    snapshot: dict[Path, bytes] = {}
    for camera_index, camera in enumerate(cameras):
        for index, frame in enumerate(frames):
            color = colors[(index + camera_index) % len(colors)]
            path = root / "cameras" / camera / "frames" / f"{frame:02d}.png"
            _write_frame(path, color)
            snapshot[path] = path.read_bytes()
    return snapshot


def _gif_pixels(path: Path) -> tuple[int, list[tuple[int, int, int, int]], list[int]]:
    image = Image.open(path)
    try:
        count = int(image.n_frames)
        pixels = []
        durations = []
        for index in range(count):
            image.seek(index)
            pixels.append(image.convert("RGBA").getpixel((2, 2)))
            durations.append(int(image.info["duration"]))
        return count, pixels, durations
    finally:
        image.close()


def test_gif_disabled_writes_nothing_and_preserves_pngs(tmp_path: Path):
    cameras = ["front_final", "side_diag"]
    frames = [7, 8]
    snapshot = _prepare_frames(tmp_path, cameras, frames)

    outputs = write_camera_previews(
        tmp_path,
        cameras,
        frames,
        fps=10,
        alias_camera="front_final",
        enabled=False,
    )

    assert outputs == []
    assert not (tmp_path / "preview.gif").exists()
    assert not any((tmp_path / "cameras" / camera / "preview.gif").exists() for camera in cameras)
    assert {path: path.read_bytes() for path in snapshot} == snapshot


def test_gif_enabled_preserves_frame_order_fps_multicamera_and_pngs(tmp_path: Path):
    cameras = ["front_final", "side_diag"]
    frames = [7, 8, 9]
    snapshot = _prepare_frames(tmp_path, cameras, frames)

    outputs = write_camera_previews(
        tmp_path,
        cameras,
        frames,
        fps=10,
        alias_camera="front_final",
        enabled=True,
    )

    front = tmp_path / "cameras/front_final/preview.gif"
    side = tmp_path / "cameras/side_diag/preview.gif"
    top = tmp_path / "preview.gif"
    assert outputs == [front, side, top]
    assert front.is_file() and side.is_file() and top.is_file()
    assert top.read_bytes() == front.read_bytes()

    front_count, front_pixels, front_durations = _gif_pixels(front)
    side_count, side_pixels, side_durations = _gif_pixels(side)
    assert front_count == len(frames)
    assert side_count == len(frames)
    assert front_pixels == [
        (255, 0, 0, 255),
        (0, 255, 0, 255),
        (0, 0, 255, 255),
    ]
    assert side_pixels == [
        (0, 255, 0, 255),
        (0, 0, 255, 255),
        (255, 0, 0, 255),
    ]
    assert front_durations == [100, 100, 100]
    assert side_durations == [100, 100, 100]
    assert {path: path.read_bytes() for path in snapshot} == snapshot
