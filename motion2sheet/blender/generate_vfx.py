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


def add_curve(name: str, points, bevel: float, material, *, z: float = 0.0) -> None:
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
        point.co = (co[0], co[1], z, 1.0)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)


def arc_points(radius: float, start_deg: float, extent_deg: float, rotation_deg: float, count: int = 64):
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


def phase_envelope(index: int, frames: int) -> tuple[float, float, float]:
    t = index / max(frames - 1, 1)
    growth = min(1.0, t / 0.58)
    decay = 0.0 if t <= 0.58 else min(1.0, (t - 0.58) / 0.42)
    if t <= 0.58:
        energy = 0.35 + 0.65 * (t / 0.58)
    else:
        energy = max(0.10, 1.0 - decay * 0.90)
    return growth, energy, decay


def setup_render(canvas: tuple[int, int], radius: float):
    scene = bpy.context.scene
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
    camera_data.ortho_scale = radius * 3.0
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
    growth, energy, decay = phase_envelope(frame_index, frames)
    setup_render(tuple(spec["canvas"]), radius)

    glow = emission_material("Glow", (0.01, 0.08, 0.55, 1.0), max(0.15, energy * float(params["glow.intensity"])))
    edge = emission_material("Edge", (0.02, 0.45, 1.0, 1.0), max(0.35, energy * 4.5))
    core = emission_material("Core", (0.92, 0.99, 1.0, 1.0), max(0.9, energy * float(params["core.intensity"])))
    spark_mat = emission_material("Spark", (0.70, 0.95, 1.0, 1.0), max(0.8, energy * 7.0))

    if decay == 0.0:
        visible_extent = max(arc_angle * 0.12, arc_angle * growth)
        visible_start = start_angle
    else:
        visible_extent = max(arc_angle * 0.22, arc_angle * (1.0 - 0.78 * decay))
        visible_start = start_angle + arc_angle * 0.58 * decay

    base_points = arc_points(radius, visible_start, visible_extent, rotation)
    add_curve("slash_glow", base_points, thickness * (2.35 + 0.35 * energy), glow, z=0.00)
    add_curve("slash_edge", base_points, thickness * (1.45 + 0.15 * energy), edge, z=0.44)
    add_curve("slash_core", base_points, thickness * max(0.24, 0.52 * energy), core, z=0.70)

    rng = random.Random(seed * 10007 + frame_index * 97)
    branch_count = max(1, round(int(params["lightning.branches"]) * max(0.35, energy)))
    jitter = float(params["lightning.jitter"])
    for branch_index in range(branch_count):
        frac = (branch_index + 1) / (branch_count + 1)
        angle = visible_start + visible_extent * frac
        anchor = point_on_arc(radius, angle, rotation)
        side = -1.0 if branch_index % 2 == 0 else 1.0
        tangent_angle = math.radians(angle + rotation + 90.0 * side)
        length = radius * (0.12 + rng.random() * 0.16) * (0.55 + energy)
        mid1 = (
            anchor[0] + math.cos(tangent_angle) * length * 0.32 + rng.uniform(-jitter, jitter) * radius,
            anchor[1] + math.sin(tangent_angle) * length * 0.32 + rng.uniform(-jitter, jitter) * radius,
            0.0,
        )
        mid2 = (
            anchor[0] + math.cos(tangent_angle) * length * 0.66 + rng.uniform(-jitter, jitter) * radius,
            anchor[1] + math.sin(tangent_angle) * length * 0.66 + rng.uniform(-jitter, jitter) * radius,
            0.0,
        )
        end = (
            anchor[0] + math.cos(tangent_angle) * length,
            anchor[1] + math.sin(tangent_angle) * length,
            0.0,
        )
        add_curve(
            f"lightning_{branch_index}",
            [anchor, mid1, mid2, end],
            thickness * max(0.18, 0.30 * energy),
            core,
            z=0.86,
        )

    spark_count = max(1, round(int(params["sparks.count"]) * max(0.18, energy)))
    spread = float(params["sparks.spread"])
    spark_size = float(params["sparks.size"])
    for spark_index in range(spark_count):
        frac = rng.random()
        angle = visible_start + visible_extent * frac
        x, y, _ = point_on_arc(radius, angle, rotation)
        x += rng.uniform(-spread, spread) * radius
        y += rng.uniform(-spread, spread) * radius
        streak_angle = math.radians(angle + rotation + rng.uniform(-70.0, 70.0))
        streak_len = radius * spark_size * (1.8 + rng.random() * 3.2) * max(0.45, energy)
        end = (x + math.cos(streak_angle) * streak_len, y + math.sin(streak_angle) * streak_len, 0.0)
        add_curve(
            f"spark_{spark_index}",
            [(x, y, 0.0), end],
            thickness * 0.12 * max(0.45, energy),
            spark_mat,
            z=0.96,
        )

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
