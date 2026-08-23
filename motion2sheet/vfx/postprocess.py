from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageFilter


def _hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def _scale_mask(mask: Image.Image, strength: float) -> Image.Image:
    factor = max(0.0, float(strength))
    return mask.point(lambda value: max(0, min(255, round(value * factor))))


def _outside_glow(mask: Image.Image, base_alpha: Image.Image, radius: float, strength: float) -> Image.Image:
    if radius <= 0.0 or strength <= 0.0:
        return Image.new("L", mask.size, 0)
    blurred = mask.filter(ImageFilter.GaussianBlur(radius=float(radius)))
    outside = ImageChops.subtract(blurred, base_alpha)
    return _scale_mask(outside, strength)


def _color_layer(size: tuple[int, int], color: str, alpha: Image.Image) -> Image.Image:
    layer = Image.new("RGBA", size, (*_hex_rgb(color), 0))
    layer.putalpha(alpha)
    return layer


def _energy_masks(frame: Image.Image) -> tuple[Image.Image, Image.Image, Image.Image, Image.Image]:
    rgba = frame.convert("RGBA")
    alpha = rgba.getchannel("A")
    inner = Image.new("L", rgba.size, 0)
    core = Image.new("L", rgba.size, 0)
    inner_data: list[int] = []
    core_data: list[int] = []
    for r, g, b, a in rgba.getdata():
        if a <= 8:
            inner_data.append(0)
            core_data.append(0)
            continue
        inner_data.append(a if b > 135 and g > 75 else 0)
        core_data.append(a if r > 190 and g > 205 and b > 210 else 0)
    inner.putdata(inner_data)
    core.putdata(core_data)
    body = alpha.point(lambda value: value if value > 16 else 0)
    return alpha, body, inner, core


def apply_glow(frame_path: Path, params: dict[str, str | float | int]) -> None:
    frame = Image.open(frame_path).convert("RGBA")
    base_alpha, body_mask, inner_mask, core_mask = _energy_masks(frame)
    outer_alpha = _outside_glow(body_mask, base_alpha, float(params["glow.outer_radius"]), float(params["glow.outer_strength"]))
    inner_alpha = _outside_glow(inner_mask, base_alpha, float(params["glow.inner_radius"]), float(params["glow.inner_strength"]))
    core_alpha = _outside_glow(core_mask, base_alpha, float(params["glow.core_radius"]), float(params["glow.core_strength"]))
    composed = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    composed = Image.alpha_composite(composed, _color_layer(frame.size, str(params["colors.outer"]), outer_alpha))
    composed = Image.alpha_composite(composed, _color_layer(frame.size, str(params["colors.inner"]), inner_alpha))
    composed = Image.alpha_composite(composed, _color_layer(frame.size, str(params["colors.core"]), core_alpha))
    composed = Image.alpha_composite(composed, frame)
    composed.save(frame_path)


def apply_glow_to_frames(frame_paths: list[Path], params: dict[str, str | float | int]) -> None:
    for frame_path in frame_paths:
        apply_glow(frame_path, params)
