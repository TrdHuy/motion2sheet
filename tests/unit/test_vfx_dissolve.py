from PIL import Image, ImageChops

from motion2sheet.vfx.dissolve import add_dissolve, dissolve_progress
from motion2sheet.vfx.spec import VfxSpec


def _frame() -> Image.Image:
    image = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
    pixels = image.load()
    for y in range(18, 78):
        for x in range(12, 84):
            if 0.6 * x + y < 112:
                pixels[x, y] = (6, 104, 255, 235)
            elif 0.6 * x + y < 126:
                pixels[x, y] = (18, 200, 255, 245)
            else:
                pixels[x, y] = (255, 255, 255, 250)
    return image


def _params(**overrides):
    values = ["dissolve.strength=0.8", "dissolve.start=0.55", "dissolve.end=1.0"]
    values.extend(f"{key}={value}" for key, value in overrides.items())
    return VfxSpec.create(template="slash", variant="lightning", overrides=values).params


def test_strength_zero_is_exact_no_op():
    frame = _frame()
    params = VfxSpec.create(template="slash", variant="lightning").params
    result = add_dissolve(frame, params, seed=42, frame_index=7, frame_count=8)
    assert result is frame
    assert result.tobytes() == frame.tobytes()


def test_frames_before_start_are_exact_no_op():
    frame = _frame()
    params = _params()
    result = add_dissolve(frame, params, seed=42, frame_index=3, frame_count=8)
    assert result is frame
    assert result.tobytes() == frame.tobytes()


def test_same_seed_and_config_are_pixel_deterministic():
    params = _params()
    first = add_dissolve(_frame(), params, seed=42891, frame_index=7, frame_count=8)
    second = add_dissolve(_frame(), params, seed=42891, frame_index=7, frame_count=8)
    assert first.tobytes() == second.tobytes()


def test_active_dissolve_breaks_main_alpha_support():
    frame = _frame()
    params = _params(fragment_count=0, spark_count=0)
    result = add_dissolve(frame, params, seed=42891, frame_index=7, frame_count=8)
    before_alpha = frame.getchannel("A")
    after_alpha = result.getchannel("A")
    assert sum(after_alpha.getdata()) < sum(before_alpha.getdata())
    diff = ImageChops.difference(before_alpha, after_alpha)
    assert diff.getbbox() is not None


def test_core_delay_keeps_core_longer_than_body():
    params = _params(core_delay=0.2)
    body = dissolve_progress(params, 5, 8)
    core = dissolve_progress(params, 5, 8, core=True)
    assert body > core
