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
    curve.bevel_resolution = 2
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, co in zip(spline.points, points):
        point.co = (co[0], co[1], z, 1.0)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)


def point_on_arc(radius: float, angle_deg: float, rotation_deg: float):
    angle = math.radians(angle_deg + rotation_deg)
    return radius * math.cos(angle), radius * math.sin(angle), 0.0


def width_envelope(t: float, power: float, flare: float) -> float:
    # Strong tapered tips with a slightly weighted leading half for a brush-stroke silhouette.
    base = max(0.0, math.sin(math.pi * t)) ** power
    lead = 1.0 + flare * (1.0 - t) * math.sin(math.pi * t)
    return base * lead


def crescent_ribbon(
    *,
    name: str,
    radius: float,
    start_deg: float,
    extent_deg: float,
    rotation_deg: float,
    half_width: float,
    material,
    z: float,
    seed: int,
    edge_noise: float,
    taper_power: float,
    flare: float,
    samples: int = 72,
) -> None:
    rng = random.Random(seed)
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []
    phase_a = rng.uniform(0.0, math.tau)
    phase_b = rng.uniform(0.0, math.tau)
    for i in range(samples):
        t = i / (samples - 1)
        angle_deg = start_deg + extent_deg * t + rotation_deg
        angle = math.radians(angle_deg)
        envelope = width_envelope(t, taper_power, flare)
        deterministic_noise = (
            math.sin(t * math.tau * 5.0 + phase_a) * 0.55
            + math.sin(t * math.tau * 11.0 + phase_b) * 0.30
            + math.sin(t * math.tau * 19.0 + phase_a * 0.7) * 0.15
        )
        noise_scale = 1.0 + deterministic_noise * edge_noise * 0.22 * envelope
        width = half_width * envelope * noise_scale
        # A gentle radial pulse keeps the body asymmetric instead of perfectly circular.
        radial = radius * (1.0 + 0.025 * edge_noise * math.sin(t * math.tau * 3.0 + phase_b))
        cx, cy = radial * math.cos(angle), radial * math.sin(angle)
        nx, ny = math.cos(angle), math.sin(angle)
        vertices.append((cx + nx * width, cy + ny * width, z))
        vertices.append((cx - nx * width, cy - ny * width, z))
        if i:
            a = 2 * (i - 1)
            b = a + 1
            c = 2 * i + 1
            d = 2 * i
            faces.append((a, b, c, d))
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)


def add_burst(name: str, radius: float, material, seed: int, z: float) -> None:
    rng = random.Random(seed)
    for i in range(12):
        angle = math.tau * i / 12.0 + rng.uniform(-0.10, 0.10)
        length = radius * rng.uniform(0.14, 0.32)
        p0 = (0.0, 0.0, 0.0)
        p1 = (math.cos(angle) * length, math.sin(angle) * length, 0.0)
        add_curve(f"{name}_{i}", [p0, p1], radius * 0.018, material, z=z)


def phase_values(index: int, frames: int, peak_t: float, decay_t: float) -> tuple[float, float, float]:
    t = index / max(frames - 1, 1)
    growth = min(1.0, t / peak_t)
    decay = 0.0 if t <= decay_t else min(1.0, (t - decay_t) / max(1e-6, 1.0 - decay_t))
    energy = (0.30 + 0.70 * growth) * (1.0 - 0.86 * decay)
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
    scene.view_settings.look = "AgX - Medium High Contrast"

    camera_data = bpy.data.cameras.new("VFXCamera")
    camera = bpy.data.objects.new("VFXCamera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = (0.0, 0.0, 10.0)
    camera.rotation_euler = (0.0, 0.0, 0.0)
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = radius * 3.35
    scene.camera = camera
    scene.world.color = (0.0, 0.0, 0.0)


def render_frame(spec: dict, output: Path, frame_index: int) -> None:
    clean_scene()
    p = spec["params"]
    radius = float(p["radius"])
    thickness = float(p["thickness"])
    arc_angle = float(p["arc_angle"])
    start_angle = float(p["start_angle"])
    rotation = float(p["rotation"])
    frames = int(spec["frames"])
    seed = int(spec["seed"])
    peak_t = float(p["timing.peak"])
    decay_t = float(p["timing.decay"])
    growth, energy, decay = phase_values(frame_index, frames, peak_t, decay_t)
    setup_render(tuple(spec["canvas"]), radius)

    outer = emission_material("Outer", (0.008, 0.035, 0.42, 1.0), max(0.25, energy * float(p["glow.intensity"])))
    inner = emission_material("Inner", (0.005, 0.45, 1.0, 1.0), max(0.7, energy * 5.8))
    core = emission_material("Core", (0.92, 1.0, 1.0, 1.0), max(1.0, energy * float(p["core.intensity"])))
    crack = emission_material("Crack", (0.70, 0.98, 1.0, 1.0), max(1.0, energy * 9.0))

    if frame_index == 0:
        add_burst("ignition", radius, core, seed, 0.90)
        visible_extent = arc_angle * 0.16
        visible_start = start_angle
    elif decay <= 0.0:
        visible_extent = max(arc_angle * 0.24, arc_angle * growth)
        visible_start = start_angle
    else:
        visible_extent = max(arc_angle * 0.20, arc_angle * (1.0 - 0.73 * decay))
        visible_start = start_angle + arc_angle * 0.50 * decay

    body_width = thickness * float(p["shape.body_scale"]) * (0.62 + 0.38 * energy)
    edge_noise = float(p["shape.edge_noise"]) * (0.55 + 0.45 * growth + 0.45 * decay)
    taper_power = float(p["shape.taper_power"])
    flare = float(p["shape.flare"])

    crescent_ribbon(
        name="outer_body", radius=radius, start_deg=visible_start, extent_deg=visible_extent,
        rotation_deg=rotation, half_width=body_width, material=outer, z=0.00,
        seed=seed * 101 + frame_index * 31, edge_noise=edge_noise,
        taper_power=taper_power, flare=flare, samples=76,
    )
    crescent_ribbon(
        name="cyan_body", radius=radius, start_deg=visible_start + visible_extent * 0.02,
        extent_deg=visible_extent * 0.96, rotation_deg=rotation,
        half_width=thickness * float(p["shape.inner_scale"]) * (0.65 + 0.35 * energy),
        material=inner, z=0.34, seed=seed * 103 + frame_index * 37,
        edge_noise=edge_noise * 0.48, taper_power=taper_power * 0.92, flare=flare * 0.65, samples=72,
    )
    crescent_ribbon(
        name="white_core", radius=radius, start_deg=visible_start + visible_extent * 0.06,
        extent_deg=visible_extent * 0.88, rotation_deg=rotation,
        half_width=thickness * float(p["shape.core_scale"]) * max(0.40, energy),
        material=core, z=0.72, seed=seed * 107 + frame_index * 41,
        edge_noise=edge_noise * 0.18, taper_power=max(0.28, taper_power * 0.75), flare=flare * 0.25, samples=68,
    )

    rng = random.Random(seed * 10007 + frame_index * 97)
    branch_count = max(2, round(int(p["lightning.branches"]) * max(0.30, energy)))
    jitter = float(p["lightning.jitter"])
    branch_length = float(p["lightning.length"])
    for i in range(branch_count):
        frac = (i + 0.7) / (branch_count + 0.4)
        angle = visible_start + visible_extent * frac
        anchor = point_on_arc(radius, angle, rotation)
        side = -1.0 if i % 2 == 0 else 1.0
        tangent = math.radians(angle + rotation + 82.0 * side)
        length = radius * branch_length * rng.uniform(0.55, 1.0) * (0.45 + 0.55 * energy)
        points = [anchor]
        for step in range(1, 4):
            f = step / 3.0
            points.append((
                anchor[0] + math.cos(tangent) * length * f + rng.uniform(-jitter, jitter) * radius * 0.45,
                anchor[1] + math.sin(tangent) * length * f + rng.uniform(-jitter, jitter) * radius * 0.45,
                0.0,
            ))
        add_curve(f"crack_{i}", points, thickness * 0.105 * max(0.55, energy), crack, z=0.94)

    spark_count = max(2, round(int(p["sparks.count"]) * max(0.16, energy)))
    for i in range(spark_count):
        frac = rng.random()
        angle = visible_start + visible_extent * frac
        x, y, _ = point_on_arc(radius, angle, rotation)
        spread = float(p["sparks.spread"]) * radius
        x += rng.uniform(-spread, spread)
        y += rng.uniform(-spread, spread)
        a = math.radians(angle + rotation + rng.uniform(-65.0, 65.0))
        length = radius * float(p["sparks.size"]) * rng.uniform(2.0, 5.5) * max(0.45, energy)
        add_curve(f"spark_{i}", [(x, y, 0.0), (x + math.cos(a) * length, y + math.sin(a) * length, 0.0)],
                  thickness * 0.085 * max(0.45, energy), crack, z=1.04)

    # Breakup fragments are deliberately strongest after the peak, matching the approved reference.
    fragment_factor = max(0.0, (frame_index / max(frames - 1, 1) - peak_t) / max(1e-6, 1.0 - peak_t))
    fragment_count = round(int(p["fragments.count"]) * fragment_factor)
    for i in range(fragment_count):
        frac = rng.random()
        angle = visible_start + visible_extent * frac
        x, y, _ = point_on_arc(radius, angle, rotation)
        spread = float(p["fragments.spread"]) * radius * (0.35 + fragment_factor)
        x += rng.uniform(-spread, spread)
        y += rng.uniform(-spread, spread)
        size = radius * float(p["fragments.size"]) * rng.uniform(0.25, 0.75) * (0.35 + fragment_factor)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=size, location=(x, y, 0.82))
        obj = bpy.context.object
        obj.name = f"fragment_{i}"
        obj.scale.x = rng.uniform(0.35, 0.70)
        obj.scale.y = rng.uniform(0.9, 1.8)
        obj.rotation_euler.z = rng.uniform(0, math.tau)
        obj.data.materials.append(inner if i % 3 else crack)

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
