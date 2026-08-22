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


def hex_rgba(value: str) -> tuple[float, float, float, float]:
    value = value.lstrip("#")
    return (
        int(value[0:2], 16) / 255.0,
        int(value[2:4], 16) / 255.0,
        int(value[4:6], 16) / 255.0,
        1.0,
    )


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


def add_triangle(name: str, points, material, *, z: float) -> None:
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata([(x, y, z) for x, y in points], [], [(0, 1, 2)])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)


def point_on_arc(radius: float, canonical_t: float, start_deg: float, arc_deg: float, rotation_deg: float):
    angle_deg = start_deg + arc_deg * canonical_t + rotation_deg
    angle = math.radians(angle_deg)
    return radius * math.cos(angle), radius * math.sin(angle), angle


def smoothstep01(value: float) -> float:
    x = max(0.0, min(1.0, value))
    return x * x * (3.0 - 2.0 * x)


def motion_window(index: int, frames: int, peak_t: float) -> tuple[float, float, float, float]:
    t = index / max(frames - 1, 1)
    if t <= peak_t:
        growth = smoothstep01(t / max(peak_t, 1e-6))
        return 0.075 * growth * growth, 0.10 + 0.90 * growth, 0.55 + 0.45 * growth, 0.0
    decay = smoothstep01((t - peak_t) / max(1e-6, 1.0 - peak_t))
    return 0.075 + 0.845 * decay, 1.0, 1.0 - 0.86 * decay, decay


def canonical_width(canonical_t: float, local_u: float, taper_power: float, flare: float) -> float:
    global_body = max(0.0, math.sin(math.pi * canonical_t)) ** max(0.18, taper_power)
    tail_taper = smoothstep01(local_u / 0.18)
    head_taper = smoothstep01((1.0 - local_u) / 0.105)
    head_bias = 1.0 + flare * smoothstep01((local_u - 0.35) / 0.45) * (1.0 - local_u)
    return global_body * tail_taper * head_taper * head_bias


def breakup_holes(seed: int, tail_t: float, head_t: float, breakup: float) -> list[tuple[float, float]]:
    if breakup < 0.28:
        return []
    rng = random.Random(seed)
    span = max(1e-5, head_t - tail_t)
    count = max(1, round(2 * breakup))
    holes = []
    max_center = min(head_t - span * 0.12, tail_t + span * (0.24 + 0.34 * breakup))
    for _ in range(count):
        center = rng.uniform(tail_t + span * 0.04, max(tail_t + span * 0.06, max_center))
        width = span * rng.uniform(0.012, 0.030) * (0.45 + 0.55 * breakup)
        holes.append((center - width, center + width))
    return holes


def in_hole(t: float, holes: list[tuple[float, float]]) -> bool:
    return any(start <= t <= end for start, end in holes)


def slash_ribbon(
    *, name: str, radius: float, start_deg: float, arc_deg: float, rotation_deg: float,
    tail_t: float, head_t: float, half_width: float, material, z: float, seed: int,
    edge_noise: float, noise_frequency: float, taper_power: float, flare: float,
    outer_noise: float, inner_noise: float, holes: list[tuple[float, float]], samples: int = 88,
) -> None:
    if head_t - tail_t <= 0.005:
        return
    rng = random.Random(seed)
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []
    phase_a = rng.uniform(0.0, math.tau)
    phase_b = rng.uniform(0.0, math.tau)
    frequency = max(0.5, noise_frequency)
    for i in range(samples):
        u = i / (samples - 1)
        canonical_t = tail_t + (head_t - tail_t) * u
        cx, cy, angle = point_on_arc(radius, canonical_t, start_deg, arc_deg, rotation_deg)
        width = half_width * canonical_width(canonical_t, u, taper_power, flare)
        layered_noise = (
            math.sin(canonical_t * math.tau * frequency * 0.42 + phase_a) * 0.46
            + math.sin(canonical_t * math.tau * frequency * 1.12 + phase_b) * 0.34
            + math.sin(canonical_t * math.tau * frequency * 2.25 + phase_a * 0.63) * 0.20
        )
        outer_w = width * (1.0 + layered_noise * edge_noise * outer_noise)
        inner_w = width * (1.0 + layered_noise * edge_noise * inner_noise)
        nx, ny = math.cos(angle), math.sin(angle)
        vertices.append((cx + nx * outer_w, cy + ny * outer_w, z))
        vertices.append((cx - nx * inner_w, cy - ny * inner_w, z))
        if i:
            midpoint_t = tail_t + (head_t - tail_t) * ((i - 0.5) / (samples - 1))
            if in_hole(midpoint_t, holes):
                continue
            a = 2 * (i - 1)
            faces.append((a, a + 1, 2 * i + 1, 2 * i))
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)


def add_energy_tongues(
    *, name: str, radius: float, start_deg: float, arc_deg: float, rotation_deg: float,
    tail_t: float, head_t: float, body_width: float, material, seed: int, amount: int,
    strength: float, breakup: float, z: float,
) -> None:
    if amount <= 0 or strength <= 0.0 or head_t - tail_t < 0.03:
        return
    rng = random.Random(seed)
    span = head_t - tail_t
    for i in range(amount):
        u = (i + rng.uniform(0.15, 0.85)) / amount
        if u < 0.10 or u > 0.94:
            continue
        canonical_t = tail_t + span * u
        cx, cy, angle = point_on_arc(radius, canonical_t, start_deg, arc_deg, rotation_deg)
        nx, ny = math.cos(angle), math.sin(angle)
        tx, ty = -math.sin(angle), math.cos(angle)
        envelope = canonical_width(canonical_t, u, 0.58, 0.18)
        if envelope < 0.05:
            continue
        base_offset = body_width * envelope * rng.uniform(0.72, 1.00)
        bx, by = cx + nx * base_offset, cy + ny * base_offset
        half_base = body_width * envelope * rng.uniform(0.08, 0.18)
        length = body_width * envelope * rng.uniform(0.30, 0.92) * strength
        backward = body_width * envelope * rng.uniform(0.30, 1.00) * (0.70 + 0.45 * breakup)
        add_triangle(
            f"{name}_{i}",
            [(bx - tx * half_base, by - ty * half_base), (bx + tx * half_base, by + ty * half_base),
             (bx + nx * length - tx * backward, by + ny * length - ty * backward)],
            material, z=z,
        )


def add_surface_cracks(
    *, radius: float, start_deg: float, arc_deg: float, rotation_deg: float, tail_t: float,
    head_t: float, material, seed: int, count: int, thickness: float, energy: float, z: float,
) -> None:
    if count <= 0 or head_t - tail_t < 0.05:
        return
    rng = random.Random(seed)
    span = head_t - tail_t
    for i in range(count):
        center = tail_t + span * rng.uniform(0.16, 0.90)
        half = span * rng.uniform(0.025, 0.065)
        points = []
        phase = rng.uniform(0.0, math.tau)
        for step in range(5):
            f = step / 4.0
            canonical_t = max(tail_t, center - half) + (min(head_t, center + half) - max(tail_t, center - half)) * f
            x, y, angle = point_on_arc(radius, canonical_t, start_deg, arc_deg, rotation_deg)
            offset = thickness * rng.uniform(-0.55, 0.55) + thickness * 0.46 * math.sin(f * math.tau * 1.5 + phase)
            points.append((x + math.cos(angle) * offset, y + math.sin(angle) * offset, 0.0))
        add_curve(f"surface_crack_{i}", points, thickness * rng.uniform(0.035, 0.060) * max(0.55, energy), material, z=z)


def add_lightning_branches(
    *, prefix: str, radius: float, start_deg: float, arc_deg: float, rotation_deg: float,
    tail_t: float, head_t: float, material, seed: int, count: int, thickness: float,
    branch_length: float, jitter: float, spread: float, energy: float, z: float,
) -> None:
    if count <= 0 or head_t - tail_t < 0.05:
        return
    rng = random.Random(seed)
    span = head_t - tail_t
    for i in range(count):
        canonical_t = tail_t + span * rng.uniform(0.18, 0.94)
        x, y, angle = point_on_arc(radius, canonical_t, start_deg, arc_deg, rotation_deg)
        nx, ny = math.cos(angle), math.sin(angle)
        tx, ty = -math.sin(angle), math.cos(angle)
        side = 1.0 if rng.random() > 0.32 else -1.0
        length = radius * branch_length * rng.uniform(0.32, 0.78) * max(0.48, energy)
        points = [(x, y, 0.0)]
        for step in range(1, 5):
            f = step / 4.0
            outward = length * f * side * (0.72 + 0.60 * spread)
            forward = length * rng.uniform(-0.25, 0.35) * f
            j = radius * jitter * rng.uniform(-0.22, 0.22)
            points.append((x + nx * outward + tx * forward + nx * j, y + ny * outward + ty * forward + ny * j, 0.0))
        add_curve(f"{prefix}_{i}", points, thickness * 0.052 * max(0.48, energy), material, z=z)


def add_directional_sparks(
    *, radius: float, start_deg: float, arc_deg: float, rotation_deg: float, tail_t: float,
    head_t: float, material, seed: int, count: int, thickness: float, spark_size: float,
    spread: float, energy: float, breakup: float, z: float,
) -> None:
    if count <= 0 or head_t - tail_t < 0.02:
        return
    rng = random.Random(seed)
    span = head_t - tail_t
    for i in range(count):
        u = 1.0 - rng.random() ** 2.0 if breakup < 0.15 else rng.random() ** 2.0
        canonical_t = tail_t + span * (0.10 + 0.84 * u)
        x, y, angle = point_on_arc(radius, canonical_t, start_deg, arc_deg, rotation_deg)
        tx, ty = -math.sin(angle), math.cos(angle)
        nx, ny = math.cos(angle), math.sin(angle)
        offset = radius * spread * rng.uniform(-0.30, 0.30)
        x, y = x + nx * offset, y + ny * offset
        length = radius * spark_size * rng.uniform(1.4, 4.2) * max(0.35, energy)
        out = rng.uniform(-0.32, 0.42)
        add_curve(
            f"spark_{i}", [(x, y, 0.0), (x + tx * length + nx * length * out, y + ty * length + ny * length * out, 0.0)],
            thickness * 0.045 * max(0.42, energy), material, z=z,
        )


def add_decay_fragments(
    *, radius: float, start_deg: float, arc_deg: float, rotation_deg: float, old_tail_t: float,
    tail_t: float, material_a, material_b, seed: int, count: int, size_param: float,
    spread_param: float, breakup: float, z: float,
) -> None:
    if breakup <= 0.0 or count <= 0 or tail_t <= old_tail_t:
        return
    rng = random.Random(seed)
    consumed_span = max(0.01, tail_t - old_tail_t)
    for i in range(count):
        canonical_t = tail_t - consumed_span * rng.random() ** 1.8
        x, y, angle = point_on_arc(radius, canonical_t, start_deg, arc_deg, rotation_deg)
        tx, ty = -math.sin(angle), math.cos(angle)
        nx, ny = math.cos(angle), math.sin(angle)
        drift = radius * spread_param * (0.10 + 0.36 * breakup)
        x += -tx * drift * rng.uniform(0.10, 0.65) + nx * drift * rng.uniform(-0.32, 0.32)
        y += -ty * drift * rng.uniform(0.10, 0.65) + ny * drift * rng.uniform(-0.32, 0.32)
        size = radius * size_param * rng.uniform(0.12, 0.36) * (0.45 + 0.60 * breakup)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=size, location=(x, y, z))
        obj = bpy.context.object
        obj.name = f"fragment_{i}"
        obj.scale.x = rng.uniform(0.20, 0.46)
        obj.scale.y = rng.uniform(0.95, 1.90)
        obj.rotation_euler.z = angle + rng.uniform(-0.6, 0.6)
        obj.data.materials.append(material_a if i % 3 else material_b)


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
    tail_t, head_t, energy, breakup = motion_window(frame_index, frames, peak_t)
    span_factor = min(1.0, (head_t - tail_t) / 0.50)
    setup_render(tuple(spec["canvas"]), radius)

    outer = emission_material("Outer", hex_rgba(str(p["colors.outer"])), max(0.20, energy * float(p["intensity.outer"])))
    body = emission_material("Body", hex_rgba(str(p["colors.body"])), max(0.30, energy * float(p["intensity.body"])))
    inner = emission_material("Inner", hex_rgba(str(p["colors.inner"])), max(0.45, energy * float(p["intensity.inner"])))
    core = emission_material("Core", hex_rgba(str(p["colors.core"])), max(0.90, energy * float(p["intensity.core"])))
    crack = emission_material("Lightning", hex_rgba(str(p["colors.lightning"])), max(0.90, energy * float(p["intensity.lightning"])))

    body_width = thickness * float(p["shape.body_scale"]) * (0.78 + 0.22 * energy)
    inner_width = thickness * float(p["shape.inner_scale"]) * (0.72 + 0.28 * energy)
    core_width = thickness * float(p["shape.core_scale"]) * (0.58 + 0.42 * energy)
    edge_noise = float(p["shape.edge_noise"]) * (0.72 + 0.20 * energy + 0.28 * breakup)
    noise_frequency = float(p["shape.edge_noise_frequency"])
    taper_power = float(p["shape.taper_power"])
    flare = float(p["shape.flare"])
    holes = breakup_holes(seed * 151 + frame_index * 59, tail_t, head_t, breakup)

    common = dict(radius=radius, start_deg=start_angle, arc_deg=arc_angle, rotation_deg=rotation,
                  tail_t=tail_t, head_t=head_t, noise_frequency=noise_frequency,
                  taper_power=taper_power, holes=holes)
    slash_ribbon(name="outer_halo", half_width=body_width * 1.20, material=outer, z=-0.08,
                 seed=seed * 97 + frame_index * 29, edge_noise=edge_noise * 0.82,
                 flare=flare, outer_noise=0.34, inner_noise=0.10, samples=96, **common)
    slash_ribbon(name="outer_body", half_width=body_width, material=body, z=0.00,
                 seed=seed * 101 + frame_index * 31, edge_noise=edge_noise,
                 flare=flare, outer_noise=0.38, inner_noise=0.11, samples=96, **common)

    tongue_amount = max(0, round(int(p["shape.tongue_count"]) * span_factor * (0.72 + 0.28 * energy)))
    add_energy_tongues(name="outer_tongue", radius=radius, start_deg=start_angle, arc_deg=arc_angle,
        rotation_deg=rotation, tail_t=tail_t, head_t=head_t, body_width=body_width, material=body,
        seed=seed * 109 + frame_index * 43, amount=tongue_amount,
        strength=float(p["shape.tongue_length"]) * (0.78 + 0.22 * energy + 0.20 * breakup), breakup=breakup, z=0.04)

    inner_tail = min(head_t - 0.003, tail_t + (head_t - tail_t) * 0.025)
    inner_head = max(tail_t + 0.003, head_t - (head_t - tail_t) * 0.025)
    slash_ribbon(name="cyan_body", radius=radius, start_deg=start_angle, arc_deg=arc_angle,
        rotation_deg=rotation, tail_t=inner_tail, head_t=inner_head, half_width=inner_width,
        material=inner, z=0.34, seed=seed * 103 + frame_index * 37, edge_noise=edge_noise * 0.38,
        noise_frequency=noise_frequency * 1.12, taper_power=max(0.30, taper_power * 0.92),
        flare=flare * 0.55, outer_noise=0.20, inner_noise=0.06, holes=holes, samples=90)

    core_tail = tail_t + (head_t - tail_t) * 0.08
    core_head = head_t - (head_t - tail_t) * 0.035
    if core_head > core_tail + 0.006:
        slash_ribbon(name="white_core", radius=radius, start_deg=start_angle, arc_deg=arc_angle,
            rotation_deg=rotation, tail_t=core_tail, head_t=core_head, half_width=core_width,
            material=core, z=0.74, seed=seed * 107 + frame_index * 41, edge_noise=edge_noise * 0.08,
            noise_frequency=noise_frequency, taper_power=max(0.22, taper_power * 0.72), flare=0.04,
            outer_noise=0.06, inner_noise=0.04, holes=holes, samples=86)

    surface_count = max(0, round(int(p["lightning.surface_crack_count"]) * energy * span_factor))
    add_surface_cracks(radius=radius, start_deg=start_angle, arc_deg=arc_angle, rotation_deg=rotation,
        tail_t=tail_t, head_t=head_t, material=crack, seed=seed * 113 + frame_index * 47,
        count=surface_count, thickness=thickness, energy=energy, z=0.92)

    branch_count = max(0, round(int(p["lightning.branch_count"]) * energy * span_factor))
    add_lightning_branches(prefix="branch", radius=radius, start_deg=start_angle, arc_deg=arc_angle,
        rotation_deg=rotation, tail_t=tail_t, head_t=head_t, material=crack,
        seed=seed * 127 + frame_index * 53, count=branch_count, thickness=thickness,
        branch_length=float(p["lightning.length"]), jitter=float(p["lightning.jitter"]),
        spread=float(p["lightning.spread"]), energy=energy, z=0.98)

    secondary_count = max(0, round(int(p["lightning.secondary_branch_count"]) * energy * span_factor))
    add_lightning_branches(prefix="secondary", radius=radius, start_deg=start_angle, arc_deg=arc_angle,
        rotation_deg=rotation, tail_t=tail_t, head_t=head_t, material=crack,
        seed=seed * 149 + frame_index * 71, count=secondary_count, thickness=thickness * 0.72,
        branch_length=float(p["lightning.length"]) * 0.58, jitter=float(p["lightning.jitter"]) * 1.18,
        spread=float(p["lightning.spread"]) * 1.15, energy=energy, z=1.01)

    spark_count = max(1, round(int(p["sparks.count"]) * (0.24 + 0.50 * energy + 0.18 * breakup)))
    add_directional_sparks(radius=radius, start_deg=start_angle, arc_deg=arc_angle, rotation_deg=rotation,
        tail_t=tail_t, head_t=head_t, material=crack, seed=seed * 131 + frame_index * 61,
        count=spark_count, thickness=thickness, spark_size=float(p["sparks.size"]),
        spread=float(p["sparks.spread"]), energy=energy, breakup=breakup, z=1.04)

    if breakup > 0.0:
        previous_tail, _, _, _ = motion_window(max(0, frame_index - 1), frames, peak_t)
        fragment_count = round(int(p["fragments.count"]) * (0.22 + 0.78 * breakup))
        add_decay_fragments(radius=radius, start_deg=start_angle, arc_deg=arc_angle, rotation_deg=rotation,
            old_tail_t=previous_tail, tail_t=tail_t, material_a=inner, material_b=crack,
            seed=seed * 137 + frame_index * 67, count=fragment_count,
            size_param=float(p["fragments.size"]), spread_param=float(p["fragments.spread"]),
            breakup=breakup, z=0.82)

    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(output)
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
