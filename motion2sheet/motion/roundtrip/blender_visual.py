from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import bpy

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from motion2sheet.motion.roundtrip.visual_contract import (
    ProjectionConfig,
    frame_numbers,
    projection_config,
    sheet_pixel,
    sheet_size,
)

RENDER_SAMPLES = 1


def _argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


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
    scene.eevee.taa_render_samples = RENDER_SAMPLES
    scene.eevee.taa_samples = RENDER_SAMPLES
    scene.eevee.use_shadows = False
    scene.eevee.use_raytracing = False
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
    frames: tuple[int, ...],
    config: ProjectionConfig,
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
        for bone_name in sorted(frame):
            bone = frame[bone_name]
            head_x, head_y = sheet_pixel(index, bone["head"], config)
            tail_x, tail_y = sheet_pixel(index, bone["tail"], config)
            head = (float(head_x), float(sheet_height - head_y), 0.0)
            tail = (float(tail_x), float(sheet_height - tail_y), 0.0)
            spline = curve.splines.new("POLY")
            spline.points.add(1)
            spline.points[0].co = (*head, 1.0)
            spline.points[1].co = (*tail, 1.0)

    obj = bpy.data.objects.new("RoundTripSkeleton", curve)
    bpy.context.scene.collection.objects.link(obj)


def _render_branch(
    name: str,
    branch: dict[str, Any],
    frames: tuple[int, ...],
    config: ProjectionConfig,
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
    frames = frame_numbers(data)
    sheet_width, sheet_height = sheet_size(len(frames))
    config = projection_config(data)

    _clear_scene()
    _configure_scene(sheet_width, sheet_height)
    material = _emission_material("RoundTripSkeletonMaterial", (0.02, 0.02, 0.02, 1.0))

    started = time.perf_counter()
    _render_branch("source", data["source"], frames, config, sheet_height, material, output)
    _render_branch("reconstructed", data["reconstructed"], frames, config, sheet_height, material, output)
    render_seconds = time.perf_counter() - started

    print(
        "motion2sheet: Blender-native skeleton sheets rendered; "
        f"frames={len(frames)}, size={sheet_width}x{sheet_height}, "
        f"samples={RENDER_SAMPLES}, renderSeconds={render_seconds:.3f} -> {output}"
    )


if __name__ == "__main__":
    main()
