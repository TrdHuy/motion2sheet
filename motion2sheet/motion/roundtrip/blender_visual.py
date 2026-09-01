from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import bpy

PANEL = 256
PADDING = 18
COLUMNS = 8


def _argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def _project(point: list[float]) -> tuple[float, float]:
    x, y, z = (float(value) for value in point)
    return x - 0.42 * y, z + 0.20 * y


def _projection_config(data: dict[str, Any]) -> dict[str, float]:
    points: list[tuple[float, float]] = []
    for branch in ("source", "reconstructed"):
        for frame in data[branch].values():
            for bone in frame.values():
                points.append(_project(bone["head"]))
                points.append(_project(bone["tail"]))
    if not points:
        raise RuntimeError("visual pose data has no points")
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = max(max_x - min_x, 1e-9)
    height = max(max_y - min_y, 1e-9)
    scale = min((PANEL - 2 * PADDING) / width, (PANEL - 2 * PADDING) / height)
    return {"minX": min_x, "maxY": max_y, "scale": scale}


def _panel_pixel(point: list[float], config: dict[str, float]) -> tuple[float, float]:
    """Map world pose to the canonical 256px visual grid before Blender rasterization.

    Pixel snapping deliberately matches the legacy Pillow proof's resolution semantics.
    Source/reconstructed world-space residuals already have strict numeric gates; the
    visual proof compares their representation at the declared raster resolution rather
    than letting sub-pixel anti-aliasing become an additional fidelity tolerance.
    """

    x, y = _project(point)
    px = PADDING + (x - config["minX"]) * config["scale"]
    py = PADDING + (config["maxY"] - y) * config["scale"]
    return float(round(px)), float(round(py))


def _clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in (bpy.data.curves, bpy.data.cameras, bpy.data.materials):
        for block in tuple(collection):
            if block.users == 0:
                collection.remove(block)


def _emission_material(name: str, rgba: tuple[float, float, float, float]):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = rgba
    emission.inputs["Strength"].default_value = 1.0
    material.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def _configure_scene(sheet_width: int, sheet_height: int) -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = sheet_width
    scene.render.resolution_y = sheet_height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False

    world = bpy.data.worlds.new("RoundTripVisualWorld") if scene.world is None else scene.world
    scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    background.inputs["Strength"].default_value = 1.0

    camera_data = bpy.data.cameras.new("RoundTripVisualCamera")
    camera = bpy.data.objects.new("RoundTripVisualCamera", camera_data)
    scene.collection.objects.link(camera)
    camera.location = (sheet_width / 2.0, sheet_height / 2.0, 100.0)
    camera.rotation_euler = (0.0, 0.0, 0.0)
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = float(sheet_height)
    camera_data.clip_start = 0.1
    camera_data.clip_end = 1000.0
    scene.camera = camera


def _remove_skeleton() -> None:
    existing = bpy.data.objects.get("RoundTripSkeleton")
    if existing is not None:
        curve = existing.data
        bpy.data.objects.remove(existing, do_unlink=True)
        if curve.users == 0:
            bpy.data.curves.remove(curve)


def _build_skeleton_sheet(
    branch: dict[str, Any],
    frames: list[int],
    config: dict[str, float],
    sheet_height: int,
    material,
) -> None:
    _remove_skeleton()
    curve = bpy.data.curves.new("RoundTripSkeletonCurve", type="CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 1
    curve.resolution_v = 0
    curve.bevel_depth = 1.0
    curve.bevel_resolution = 0
    curve.materials.append(material)

    for index, frame_number in enumerate(frames):
        frame = branch[str(frame_number)]
        column = index % COLUMNS
        row = index // COLUMNS
        for bone_name in sorted(frame):
            bone = frame[bone_name]
            head_x, head_y = _panel_pixel(bone["head"], config)
            tail_x, tail_y = _panel_pixel(bone["tail"], config)
            head = (
                column * PANEL + head_x,
                sheet_height - (row * PANEL + head_y),
                0.0,
            )
            tail = (
                column * PANEL + tail_x,
                sheet_height - (row * PANEL + tail_y),
                0.0,
            )
            spline = curve.splines.new("POLY")
            spline.points.add(1)
            spline.points[0].co = (*head, 1.0)
            spline.points[1].co = (*tail, 1.0)

    obj = bpy.data.objects.new("RoundTripSkeleton", curve)
    bpy.context.scene.collection.objects.link(obj)


def _render_branch(
    name: str,
    branch: dict[str, Any],
    frames: list[int],
    config: dict[str, float],
    sheet_height: int,
    material,
    output: Path,
) -> None:
    _build_skeleton_sheet(branch, frames, config, sheet_height, material)
    bpy.context.scene.render.filepath = str(output / f"{name}_sheet.png")
    bpy.ops.render.render(write_still=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(_argv())

    pose_path = Path(args.input).resolve()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    data = json.loads(pose_path.read_text(encoding="utf-8"))
    start, end = data["frameRange"]
    frames = list(range(int(start), int(end) + 1))
    if not frames:
        raise RuntimeError("visual pose data has no frames")

    rows = math.ceil(len(frames) / COLUMNS)
    sheet_width = PANEL * COLUMNS
    sheet_height = PANEL * rows
    config = _projection_config(data)

    _clear_scene()
    _configure_scene(sheet_width, sheet_height)
    material = _emission_material("RoundTripSkeletonMaterial", (0.02, 0.02, 0.02, 1.0))
    _render_branch("source", data["source"], frames, config, sheet_height, material, output)
    _render_branch("reconstructed", data["reconstructed"], frames, config, sheet_height, material, output)
    print(
        "motion2sheet: Blender-native skeleton sheets rendered; "
        f"frames={len(frames)}, size={sheet_width}x{sheet_height} -> {output}"
    )


if __name__ == "__main__":
    main()
