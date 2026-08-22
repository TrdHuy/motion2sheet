"""Deterministic Blender-side VFX renderer for vfx2sheet."""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

import bpy


def argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args(argv())


def clean_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.curves, bpy.data.meshes, bpy.data.materials, bpy.data.cameras):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)


def emission_material(name: str, color: tuple[float, float, float, float], strength: float):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = color
    emission.inputs["Strength"].default_value = strength
    mat.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return mat


def add_curve(name: str, points, bevel: float, material) -> None:
    if len(points) < 2 or bevel <= 0:
        return
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 2
    curve.bevel_depth = bevel
    curve.bevel_resolution = 3
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, co in zip(spline.points, points):
        point.co = (co[0], co[1], co[2], 1.0)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)


def arc_points(radius: float, start_deg: float, extent_deg: float, rotation_deg: float, count: int = 48):
    points = []
    total = max(2, count)
    for index in range(total):
        t = index / (total - 1)
        angle = math.radians(start_deg + extent_deg * t + rotation_deg)
        points.append((radius * math.cos(angle), radius * math.sin(angle), 0.0))
    return points


def point_on_arc(radius: float, angle_deg: float, rotation_deg: float):
    angle = math.radians(angle_deg + rotation_deg)
    return radius * math.cos(angle), radius * math.sin(angle), 0.0


def phase_envelope(index: int, frames: int) -> tuple[float, float]:
    t = index / max(frames - 1, 1)
    growth = min(1.0, t / 0.58)
    if t <= 0.58:
        energy = 0.35 + 0.65 * (t / 0.58)
    else:
        energy = max(0.12, 1.0 - (t - 0.58) / 0.42 * 0.88)
    return growth, energy


def setup_render(canvas: tuple[int, int], radius: float):
    scene = bpy.context.scene
    # Eevee requires EGL/OpenGL even in background mode on GitHub runners.
    # Cycles CPU renders without a display server and keeps CI deterministic.
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 8
    scene.cycles.use_denoising = False
    scene.render.resolution_x = canvas[0]
    scene.render.resolution_y = canvas[1]
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = True

    camera_data = bpy.data.cameras.new("VFXCamera")
    camera = bpy.data.objects.new("VFXCamera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = (0.0, 0.0, 10.0)
    camera.rotation_euler = (0.0, 0.0, 0.0)
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = radius * 2.9
    scene.camera = camera
    scene.world.color = (0.0, 0.0, 0.0)


def render_frame(spec: dict, output: Path, frame_index: int) -> None:
    clean_scene()
    params = spec["params"]
    radius = float(params["radius"])
    thickness = float(params["thickness"])
    arc_angle = float(params["arc_angle"])
    start_angle = float(params["start_angle"])
    rotation = float(params["rotation"])
    frames = int(spec["frames"])
    seed = int(spec["seed"])
    growth, energy = phase_envelope(frame_index, frames)
    setup_render(tuple(spec["canvas"]), radius)

    glow = emission_material("Glow", (0.02, 0.20, 1.0, 1.0), max(0.25, energy * float(params["glow.intensity"])))
    edge = emission_material("Edge", (0.05, 0.65, 1.0, 1.0), max(0.5, energy * 4.0))
    core = emission_material("Core", (0.80, 0.96, 1.0, 1.0), max(0.8, energy * float(params["core.intensity"])))
    spark_mat = emission_material("Spark", (0.65, 0.90, 1.0, 1.0), max(0.8, energy * 6.0))

    visible_extent = max(arc_angle * 0.12, arc_angle * growth)
    base_points = arc_points(radius, start_angle, visible_extent, rotation)
    add_curve("slash_glow", base_points, thickness * (1.9 + 0.5 * energy), glow)
    add_curve("slash_edge", base_points, thickness * (1.25 + 0.2 * energy), edge)
    add_curve("slash_core", base_points, thickness * max(0.38, 0.66 * energy), core)

    rng = random.Random(seed * 10007 + frame_index * 97)
    branch_count = max(0, round(int(params["lightning.branches"]) * energy))
    jitter = float(params["lightning.jitter"])
    for branch_index in range(branch_count):
        frac = (branch_index + 1) / (branch_count + 1)
        angle = start_angle + visible_extent * frac
        anchor = point_on_arc(radius, angle, rotation)
        tangent_angle = math.radians(angle + rotation + rng.choice((-90.0, 90.0)))
        length = radius * (0.10 + rng.random() * 0.14) * (0.6 + energy)
        mid = (
            anchor[0] + math.cos(tangent_angle) * length * 0.52 + rng.uniform(-jitter, jitter) * radius,
            anchor[1] + math.sin(tangent_angle) * length * 0.52 + rng.uniform(-jitter, jitter) * radius,
            0.0,
        )
        end = (
            anchor[0] + math.cos(tangent_angle) * length,
            anchor[1] + math.sin(tangent_angle) * length,
            0.0,
        )
        add_curve(f"lightning_{branch_index}", [anchor, mid, end], thickness * 0.28, core)

    spark_count = max(1, round(int(params["sparks.count"]) * energy))
    spread = float(params["sparks.spread"])
    spark_size = float(params["sparks.size"])
    for spark_index in range(spark_count):
        frac = rng.random() * max(growth, 0.15)
        angle = start_angle + arc_angle * frac
        x, y, _ = point_on_arc(radius, angle, rotation)
        x += rng.uniform(-spread, spread) * radius
        y += rng.uniform(-spread, spread) * radius
        size = spark_size * (0.55 + rng.random() * 0.9) * max(0.35, energy)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=size, location=(x, y, 0.0))
        spark = bpy.context.object
        spark.name = f"spark_{spark_index}"
        spark.data.materials.append(spark_mat)

    output.parent.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.render.filepath = str(output)
    bpy.ops.render.render(write_still=True)


def main() -> None:
    args = parse_args()
    spec_path = Path(args.spec).resolve()
    output_root = Path(args.output).resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if spec.get("template") != "slash" or spec.get("variant") != "lightning":
        raise RuntimeError("Blender MVP supports only slash/lightning")
    frames_dir = output_root / "frames"
    for index in range(int(spec["frames"])):
        render_frame(spec, frames_dir / f"{index + 1:02d}.png", index)
    print(f"vfx2sheet: rendered {spec['frames']} deterministic frame(s) -> {frames_dir}")


if __name__ == "__main__":
    main()
