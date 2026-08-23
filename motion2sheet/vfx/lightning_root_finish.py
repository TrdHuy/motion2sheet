from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .energy_graph import build_energy_graph


def _hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def _mask_layer(mask: Image.Image, color: tuple[int, int, int], amount: float) -> Image.Image:
    alpha = mask.point(lambda value: max(0, min(255, round(value * amount))))
    layer = Image.new("RGBA", mask.size, (*color, 0))
    layer.putalpha(alpha)
    return layer


def _draw_root(mask: Image.Image, points: list[tuple[float, float]], widths: list[float], value: int, scale: int) -> None:
    draw = ImageDraw.Draw(mask)
    for index in range(len(points) - 1):
        width = max(1, round((widths[index] + widths[index + 1]) * 0.5 * scale))
        draw.line(
            [
                (points[index][0] * scale, points[index][1] * scale),
                (points[index + 1][0] * scale, points[index + 1][1] * scale),
            ],
            fill=value,
            width=width,
        )


def add_lightning_root_finish(
    frame: Image.Image,
    params: dict[str, str | float | int],
    *,
    seed: int,
    frame_index: int,
    frame_count: int,
) -> Image.Image:
    graph = build_energy_graph(frame.size, params, seed=seed, frame_index=frame_index, frame_count=frame_count)
    if graph.energy < 0.56 or graph.breakup > 0.92:
        return frame.convert("RGBA")

    requested = max(2, min(4, int(params["lightning.major_count"])))
    count = max(1, round(requested * (0.82 + 0.18 * graph.energy) * (1.0 - graph.breakup * 0.56)))
    rng = random.Random(seed * 524287 + frame_index * 12289 + 1877)
    anchors = graph.major_anchor_indices(count, rng)

    scale = 3
    large = (frame.width * scale, frame.height * scale)
    roots = Image.new("L", large, 0)
    for bolt_index, anchor in enumerate(anchors):
        life_rng = random.Random(seed * 900001 + bolt_index * 3571)
        if graph.breakup > life_rng.uniform(0.62, 1.08):
            continue
        node = graph.nodes[anchor]
        side = -1.0 if bolt_index % 2 == 0 else 1.0
        nx, ny = node.normal[0] * side, node.normal[1] * side
        tx, ty = node.tangent
        # Three short points span deep-body -> core edge -> existing bolt root.
        # They remain inside accepted alpha support, so this is visual integration
        # rather than a new external lightning branch.
        points = [
            (node.point[0] - nx * node.width * 0.34 - tx * node.width * 0.08,
             node.point[1] - ny * node.width * 0.34 - ty * node.width * 0.08),
            (node.point[0] - nx * node.width * 0.06,
             node.point[1] - ny * node.width * 0.06),
            (node.point[0] + nx * node.width * 0.43,
             node.point[1] + ny * node.width * 0.43),
        ]
        base = max(0.8, node.width * 0.13)
        widths = [base * 1.25, base, max(0.45, base * 0.58)]
        _draw_root(roots, points, widths, 188, scale)

    roots = roots.resize(frame.size, Image.Resampling.LANCZOS)
    # Clip strictly to already-existing effect support. The root pass cannot grow
    # the silhouette or alter terminal plume geometry.
    support = frame.convert("RGBA").getchannel("A").point(lambda value: 255 if value >= 20 else 0)
    roots = ImageChops.multiply(roots, support)

    inner = _hex_rgb(str(params["colors.inner"]))
    lightning = _hex_rgb(str(params["colors.lightning"]))
    result = frame.convert("RGBA")
    result = Image.alpha_composite(result, _mask_layer(roots.filter(ImageFilter.GaussianBlur(2.0)), inner, 0.23))
    result = Image.alpha_composite(result, _mask_layer(roots.filter(ImageFilter.GaussianBlur(0.34)), inner, 0.46))
    # A very small hot center preserves continuity with the external bolt while
    # leaving most of the buried root cyan rather than white.
    hot = roots.filter(ImageFilter.MinFilter(3))
    result = Image.alpha_composite(result, _mask_layer(hot, lightning, 0.16))
    return result


def apply_lightning_root_finish_to_frames(
    frame_paths: list[Path],
    params: dict[str, str | float | int],
    *,
    seed: int,
) -> None:
    frame_count = len(frame_paths)
    for frame_index, frame_path in enumerate(frame_paths):
        frame = Image.open(frame_path).convert("RGBA")
        add_lightning_root_finish(
            frame,
            params,
            seed=seed,
            frame_index=frame_index,
            frame_count=frame_count,
        ).save(frame_path)
