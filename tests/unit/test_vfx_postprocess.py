from PIL import Image

from motion2sheet.vfx.postprocess import apply_glow
from motion2sheet.vfx.spec import VfxSpec


def test_glow_is_deterministic_and_stays_under_source_pixels(tmp_path):
    source = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    for y in range(24, 40):
        for x in range(20, 44):
            source.putpixel((x, y), (0, 72, 255, 255))
    for y in range(29, 35):
        for x in range(25, 39):
            source.putpixel((x, y), (255, 255, 255, 255))

    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    source.save(first)
    source.save(second)
    params = VfxSpec.create(template="slash", variant="lightning").params

    apply_glow(first, params)
    apply_glow(second, params)
    first_image = Image.open(first).convert("RGBA")
    second_image = Image.open(second).convert("RGBA")

    assert list(first_image.getdata()) == list(second_image.getdata())
    assert first_image.getpixel((32, 32)) == (255, 255, 255, 255)
    assert first_image.getpixel((18, 32))[3] > 0
