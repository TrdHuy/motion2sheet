from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageFilter


def _hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def _scale_mask(mask: Image.Image, strength: float) -> Image.Image:
    factor = max(0.0, float(strength))
    return mask.point(lambda value: max(0, min(255, round(value * factor))))


def _external_lightning_mask(frame: Image.Image) -> Image.Image:
    rgba = frame.convert("RGBA")
    pixels = list(rgba.getdata())
    body = Image.new("L", rgba.size, 0)
    bright = Image.new("L", rgba.size, 0)
    body.putdata([
        255 if a > 64 and b > 110 and b >= r * 1.22 and not (r > 178 and g > 190 and b > 198) else 0
        for r, g, b, a in pixels
    ])
    bright.putdata([
        a if a > 28 and b > 170 and g > 155 and (r > 135 or g > 205) else 0
        for r, g, b, a in pixels
    ])
    # Keep body-adjacent bolt roots but reject the white/cyan core corridor itself.
    body_guard = body.filter(ImageFilter.MaxFilter(5))
    outside = ImageChops.subtract(bright, body_guard)
    return outside


def apply_external_lightning_glow(frame_path: Path, params: dict[str, str | float | int]) -> None:
    frame = Image.open(frame_path).convert("RGBA")
    radius = float(params["lightning.glow_radius"])
    strength = float(params["lightning.glow_strength"])
    if radius <= 0.0 or strength <= 0.0:
        return
    mask = _external_lightning_mask(frame)
    blurred = mask.filter(ImageFilter.GaussianBlur(radius=radius))
    halo_alpha = _scale_mask(blurred, strength)
    halo = Image.new("RGBA", frame.size, (*_hex_rgb(str(params["colors.inner"])), 0))
    halo.putalpha(halo_alpha)
    composed = Image.alpha_composite(halo, frame)
    composed.save(frame_path)


def apply_external_lightning_glow_to_frames(
    frame_paths: list[Path],
    params: dict[str, str | float | int],
) -> None:
    for frame_path in frame_paths:
        apply_external_lightning_glow(frame_path, params)
