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
    return (int(value[0:2], 16) / 255.0, int(value[2:4], 16) / 255.0, int(value[4:6], 16) / 255.0, 1.0)


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


def add_polygon(name: str, points, material, *, z: float) -> None:
    if len(points) < 3:
        return
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata([(x, y, z) for x, y in points], [], [tuple(range(len(points)))])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)


def point_on_arc(radius: float, canonical_t: float, start_deg: float, arc_deg: float, rotation_deg: float):
    angle = math.radians(start_deg + arc_deg * canonical_t + rotation_deg)
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
    if breakup < 0.30:
        return []
    rng = random.Random(seed)
    span = max(1e-5, head_t - tail_t)
    count = 1 + round(3 * breakup)
    holes: list[tuple[float, float]] = []
    for _ in range(count):
        center = tail_t + span * rng.uniform(0.05, min(0.78, 0.26 + 0.55 * breakup))
        width = span * rng.uniform(0.010, 0.026) * (0.60 + 0.60 * breakup)
        holes.append((center - width, center + width))
    return holes


def in_hole(t: float, holes: list[tuple[float, float]]) -> bool:
    return any(start <= t <= end for start, end in holes)


def path_form_offset(canonical_t: float, radius: float, form_noise: float, form_frequency: float, path_seed: int) -> float:
    rng = random.Random(path_seed)
    phase_a = rng.uniform(0.0, math.tau)
    phase_b = rng.uniform(0.0, math.tau)
    wave = math.sin(canonical_t * math.tau * form_frequency + phase_a) * 0.68 + math.sin(canonical_t * math.tau * form_frequency * 0.53 + phase_b) * 0.32
    return radius * 0.032 * form_noise * wave * max(0.0, math.sin(math.pi * canonical_t))


def slash_ribbon(*, name: str, radius: float, start_deg: float, arc_deg: float, rotation_deg: float,
    tail_t: float, head_t: float, half_width: float, material, z: float, seed: int, path_seed: int,
    form_noise: float, form_frequency: float, edge_noise: float, noise_frequency: float,
    detail_noise: float, detail_frequency: float, taper_power: float, flare: float,
    outer_noise: float, inner_noise: float, holes: list[tuple[float, float]], samples: int = 104) -> None:
    if head_t - tail_t <= 0.005:
        return
    rng = random.Random(seed)
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []
    phase_a = rng.uniform(0.0, math.tau)
    phase_b = rng.uniform(0.0, math.tau)
    phase_c = rng.uniform(0.0, math.tau)
    for i in range(samples):
        u = i / (samples - 1)
        canonical_t = tail_t + (head_t - tail_t) * u
        cx, cy, angle = point_on_arc(radius, canonical_t, start_deg, arc_deg, rotation_deg)
        nx, ny = math.cos(angle), math.sin(angle)
        center_shift = path_form_offset(canonical_t, radius, form_noise, form_frequency, path_seed)
        cx += nx * center_shift
        cy += ny * center_shift
        width = half_width * canonical_width(canonical_t, u, taper_power, flare)
        mid_wave = (
            math.sin(canonical_t * math.tau * noise_frequency * 0.42 + phase_a) * 0.46
            + math.sin(canonical_t * math.tau * noise_frequency * 1.08 + phase_b) * 0.34
            + math.sin(canonical_t * math.tau * noise_frequency * 1.75 + phase_c) * 0.20
        )
        detail_wave = (
            math.sin(canonical_t * math.tau * detail_frequency + phase_c * 0.71) * 0.58
            + math.sin(canonical_t * math.tau * detail_frequency * 1.71 + phase_a * 0.37) * 0.42
        )
        outer_w = max(0.0, width * (1.0 + mid_wave * edge_noise * outer_noise + detail_wave * detail_noise * outer_noise * 0.34))
        inner_w = max(0.0, width * (1.0 + mid_wave * edge_noise * inner_noise + detail_wave * detail_noise * inner_noise * 0.18))
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


def add_energy_tongues(*, name: str, radius: float, start_deg: float, arc_deg: float, rotation_deg: float,
    tail_t: float, head_t: float, body_width: float, material, seed: int, amount: int,
    strength: float, curve_amount: float, width_scale: float, breakup: float, z: float) -> None:
    if amount <= 0 or strength <= 0.0 or head_t - tail_t < 0.03:
        return
    rng = random.Random(seed)
    span = head_t - tail_t
    for i in range(amount):
        u = (i + rng.uniform(0.18, 0.82)) / amount
        if u < 0.08 or u > 0.95:
            continue
        canonical_t = tail_t + span * u
        cx, cy, angle = point_on_arc(radius, canonical_t, start_deg, arc_deg, rotation_deg)
        nx, ny = math.cos(angle), math.sin(angle)
        tx, ty = -math.sin(angle), math.cos(angle)
        envelope = canonical_width(canonical_t, u, 0.58, 0.18)
        if envelope < 0.05:
            continue
        base_offset = body_width * envelope * rng.uniform(0.76, 0.98)
        bx, by = cx + nx * base_offset, cy + ny * base_offset
        half_base = body_width * envelope * rng.uniform(0.07, 0.14) * width_scale
        length = body_width * envelope * rng.uniform(0.34, 0.92) * strength
        backward = body_width * envelope * rng.uniform(0.24, 0.82) * (0.75 + 0.45 * breakup)
        bend = body_width * envelope * rng.uniform(-0.55, 0.55) * curve_amount
        mid_x = bx + nx * length * 0.52 - tx * backward * 0.30 + tx * bend * 0.55
        mid_y = by + ny * length * 0.52 - ty * backward * 0.30 + ty * bend * 0.55
        tip_x = bx + nx * length - tx * backward + tx * bend
        tip_y = by + ny * length - ty * backward + ty * bend
        mid_half = half_base * rng.uniform(0.32, 0.52)
        add_polygon(f"{name}_{i}", [
            (bx - tx * half_base, by - ty * half_base),
            (mid_x - tx * mid_half, mid_y - ty * mid_half), (tip_x, tip_y),
            (mid_x + tx * mid_half, mid_y + ty * mid_half),
            (bx + tx * half_base, by + ty * half_base),
        ], material, z=z)


def clustered_t(rng: random.Random, low: float, high: float, cluster_strength: float, clusters: list[float]) -> float:
    if clusters and rng.random() < cluster_strength:
        center = clusters[rng.randrange(len(clusters))]
        return max(low, min(high, rng.gauss(center, (high - low) * 0.065)))
    return rng.uniform(low, high)


def add_surface_cracks(*, radius: float, start_deg: float, arc_deg: float, rotation_deg: float, tail_t: float,
    head_t: float, material, seed: int, count: int, thickness: float, width_scale: float,
    energy: float, z: float) -> None:
    if count <= 0 or head_t - tail_t < 0.05:
        return
    rng = random.Random(seed)
    span = head_t - tail_t
    for i in range(count):
        center = tail_t + span * rng.uniform(0.14, 0.92)
        half = span * rng.uniform(0.022, 0.060)
        start = max(tail_t, center - half)
        end = min(head_t, center + half)
        phase = rng.uniform(0.0, math.tau)
        points = []
        for step in range(6):
            f = step / 5.0
            canonical_t = start + (end - start) * f
            x, y, angle = point_on_arc(radius, canonical_t, start_deg, arc_deg, rotation_deg)
            offset = thickness * rng.uniform(-0.52, 0.52) + thickness * 0.44 * math.sin(f * math.tau * 1.65 + phase)
            points.append((x + math.cos(angle) * offset, y + math.sin(angle) * offset, 0.0))
        add_curve(f"surface_crack_{i}", points, thickness * 0.050 * width_scale * max(0.52, energy), material, z=z)


def add_lightning_branches(*, prefix: str, radius: float, start_deg: float, arc_deg: float, rotation_deg: float,
    tail_t: float, head_t: float, body_width: float, material, seed: int, count: int,
    thickness: float, width_scale: float, branch_length: float, jitter: float, spread: float,
    edge_bias: float, cluster_strength: float, energy: float, z: float) -> None:
    if count <= 0 or head_t - tail_t < 0.05:
        return
    rng = random.Random(seed)
    span = head_t - tail_t
    clusters = [rng.uniform(0.24, 0.88) for _ in range(3)]
    for i in range(count):
        local_u = clustered_t(rng, 0.14, 0.96, cluster_strength, clusters)
        canonical_t = tail_t + span * local_u
        x, y, angle = point_on_arc(radius, canonical_t, start_deg, arc_deg, rotation_deg)
        nx, ny = math.cos(angle), math.sin(angle)
        tx, ty = -math.sin(angle), math.cos(angle)
        side = 1.0 if rng.random() > 0.26 else -1.0
        envelope = canonical_width(canonical_t, local_u, 0.58, 0.18)
        start_offset = body_width * envelope * edge_bias * side
        x += nx * start_offset
        y += ny * start_offset
        length = radius * branch_length * rng.uniform(0.28, 0.76) * max(0.44, energy)
        points = [(x, y, 0.0)]
        walk_x, walk_y = x, y
        for step in range(1, 6):
            f = step / 5.0
            segment = length / 5.0
            outward = segment * side * (0.78 + 0.58 * spread)
            forward = segment * rng.uniform(-0.34, 0.46)
            zigzag = radius * jitter * rng.uniform(-0.055, 0.055) * (0.7 + 0.6 * f)
            walk_x += nx * outward + tx * forward + tx * zigzag
            walk_y += ny * outward + ty * forward + ty * zigzag
            points.append((walk_x, walk_y, 0.0))
        add_curve(f"{prefix}_{i}", points, thickness * 0.067 * width_scale * max(0.46, energy), material, z=z)


def add_directional_sparks(*, radius: float, start_deg: float, arc_deg: float, rotation_deg: float, tail_t: float,
    head_t: float, material, seed: int, count: int, thickness: float, spark_size: float,
    spread: float, energy: float, breakup: float, z: float) -> None:
    if count <= 0 or head_t - tail_t < 0.02:
        return
    rng = random.Random(seed)
    span = head_t - tail_t
    for i in range(count):
        u = 1.0 - rng.random() ** 2.0 if breakup < 0.18 else rng.random() ** 2.0
        canonical_t = tail_t + span * (0.08 + 0.86 * u)
        x, y, angle = point_on_arc(radius, canonical_t, start_deg, arc_deg, rotation_deg)
        tx, ty = -math.sin(angle), math.cos(angle)
        nx, ny = math.cos(angle), math.sin(angle)
        offset = radius * spread * rng.uniform(-0.31, 0.31)
        x, y = x + nx * offset, y + ny * offset
        length = radius * spark_size * rng.uniform(1.3, 4.4) * max(0.32, energy)
        out = rng.uniform(-0.34, 0.44)
        add_curve(f"spark_{i}", [(x, y, 0.0), (x + tx * length + nx * length * out, y + ty * length + ny * length * out, 0.0)], thickness * 0.050 * max(0.40, energy), material, z=z)


def add_decay_fragments(*, radius: float, start_deg: float, arc_deg: float, rotation_deg: float, old_tail_t: float,
    tail_t: float, material_a, material_b, seed: int, count: int, size_param: float,
    spread_param: float, breakup: float, z: float) -> None:
    if breakup <= 0.0 or count <= 0 or tail_t <= old_tail_t:
        return
    rng = random.Random(seed)
    consumed_span = max(0.01, tail_t - old_tail_t)
    for i in range(count):
        canonical_t = tail_t - consumed_span * rng.random() ** 1.8
        x, y, angle = point_on_arc(radius, canonical_t, start_deg, arc_deg, rotation_deg)
        tx, ty = -math.sin(angle), math.cos(angle)
        nx, ny = math.cos(angle), math.sin(angle)
        drift = radius * spread_param * (0.10 + 0.40 * breakup)
        x += -tx * drift * rng.uniform(0.10, 0.68) + nx * drift * rng.uniform(-0.34, 0.34)
        y += -ty * drift * rng.uniform(0.10, 0.68) + ny * drift * rng.uniform(-0.34, 0.34)
        size = radius * size_param * rng.uniform(0.10, 0.30) * (0.40 + 0.65 * breakup)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=size, location=(x, y, z))
        obj = bpy.context.object
        obj.name = f"fragment_{i}"
        obj.scale.x = rng.uniform(0.16, 0.38)
        obj.scale.y = rng.uniform(1.05, 2.10)
        obj.rotation_euler.z = angle + rng.uniform(-0.75, 0.75)
        obj.data.materials.append(material_a if i % 3 else material_b)


def setup_render(canvas: tuple[int, int], radius: float) -> None:
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

    outer = emission_material("Outer", hex_rgba(str(p["colors.outer"])), max(0.18, energy * float(p["intensity.outer"])))
    body = emission_material("Body", hex_rgba(str(p["colors.body"])), max(0.24, energy * float(p["intensity.body"])))
    inner = emission_material("Inner", hex_rgba(str(p["colors.inner"])), max(0.36, energy * float(p["intensity.inner"])))
    core = emission_material("Core", hex_rgba(str(p["colors.core"])), max(0.75, energy * float(p["intensity.core"])))
    crack = emission_material("Lightning", hex_rgba(str(p["colors.lightning"])), max(0.78, energy * float(p["intensity.lightning"])))

    body_width = thickness * float(p["shape.body_scale"]) * (0.78 + 0.22 * energy)
    inner_width = thickness * float(p["shape.inner_scale"]) * (0.72 + 0.28 * energy)
    core_width = thickness * float(p["shape.core_scale"]) * (0.56 + 0.44 * energy)
    edge_noise = float(p["shape.edge_noise"]) * (0.70 + 0.22 * energy + 0.30 * breakup)
    path_seed = seed * 89 + frame_index * 17
    internal_holes = breakup_holes(seed * 151 + frame_index * 59, tail_t, head_t, breakup)
    core_holes = breakup_holes(seed * 157 + frame_index * 73, tail_t, head_t, min(1.0, breakup * 1.22))

    shared = dict(radius=radius, start_deg=start_angle, arc_deg=arc_angle, rotation_deg=rotation,
        tail_t=tail_t, head_t=head_t, path_seed=path_seed,
        form_noise=float(p["shape.form_noise"]), form_frequency=float(p["shape.form_noise_frequency"]),
        noise_frequency=float(p["shape.edge_noise_frequency"]), detail_noise=float(p["shape.detail_noise"]),
        detail_frequency=float(p["shape.detail_noise_frequency"]), taper_power=float(p["shape.taper_power"]))
    slash_ribbon(name="outer_halo", half_width=body_width * 1.18, material=outer, z=-0.08,
        seed=seed * 97 + frame_index * 29, edge_noise=edge_noise * 0.76,
        flare=float(p["shape.flare"]), outer_noise=0.32, inner_noise=0.08, holes=[], samples=112, **shared)
    slash_ribbon(name="outer_body", half_width=body_width, material=body, z=0.00,
        seed=seed * 101 + frame_index * 31, edge_noise=edge_noise,
        flare=float(p["shape.flare"]), outer_noise=0.34, inner_noise=0.09, holes=[], samples=112, **shared)

    tongue_amount = max(0, round(int(p["shape.tongue_count"]) * span_factor * (0.72 + 0.28 * energy)))
    add_energy_tongues(name="outer_tongue", radius=radius, start_deg=start_angle, arc_deg=arc_angle,
        rotation_deg=rotation, tail_t=tail_t, head_t=head_t, body_width=body_width, material=body,
        seed=seed * 109 + frame_index * 43, amount=tongue_amount,
        strength=float(p["shape.tongue_length"]) * (0.76 + 0.24 * energy + 0.18 * breakup),
        curve_amount=float(p["shape.tongue_curve"]), width_scale=float(p["shape.tongue_width"]), breakup=breakup, z=0.04)

    inner_tail = min(head_t - 0.003, tail_t + (head_t - tail_t) * 0.025)
    inner_head = max(tail_t + 0.003, head_t - (head_t - tail_t) * 0.025)
    slash_ribbon(name="cyan_body", radius=radius, start_deg=start_angle, arc_deg=arc_angle, rotation_deg=rotation,
        tail_t=inner_tail, head_t=inner_head, half_width=inner_width, material=inner, z=0.34,
        seed=seed * 103 + frame_index * 37, path_seed=path_seed,
        form_noise=float(p["shape.form_noise"]), form_frequency=float(p["shape.form_noise_frequency"]),
        edge_noise=edge_noise * 0.34, noise_frequency=float(p["shape.edge_noise_frequency"]) * 1.08,
        detail_noise=float(p["shape.detail_noise"]) * 0.48, detail_frequency=float(p["shape.detail_noise_frequency"]),
        taper_power=max(0.30, float(p["shape.taper_power"]) * 0.92), flare=float(p["shape.flare"]) * 0.52,
        outer_noise=0.17, inner_noise=0.05, holes=internal_holes, samples=104)

    core_tail = tail_t + (head_t - tail_t) * 0.08
    core_head = head_t - (head_t - tail_t) * 0.035
    if core_head > core_tail + 0.006:
        slash_ribbon(name="white_core", radius=radius, start_deg=start_angle, arc_deg=arc_angle, rotation_deg=rotation,
            tail_t=core_tail, head_t=core_head, half_width=core_width, material=core, z=0.74,
            seed=seed * 107 + frame_index * 41, path_seed=path_seed,
            form_noise=float(p["shape.form_noise"]), form_frequency=float(p["shape.form_noise_frequency"]),
            edge_noise=edge_noise * 0.06, noise_frequency=float(p["shape.edge_noise_frequency"]),
            detail_noise=float(p["shape.detail_noise"]) * 0.12, detail_frequency=float(p["shape.detail_noise_frequency"]),
            taper_power=max(0.22, float(p["shape.taper_power"]) * 0.72), flare=0.03,
            outer_noise=0.05, inner_noise=0.03, holes=core_holes, samples=100)

    surface_count = max(0, round(int(p["lightning.surface_crack_count"]) * energy * span_factor))
    add_surface_cracks(radius=radius, start_deg=start_angle, arc_deg=arc_angle, rotation_deg=rotation,
        tail_t=tail_t, head_t=head_t, material=crack, seed=seed * 113 + frame_index * 47,
        count=surface_count, thickness=thickness, width_scale=float(p["lightning.surface_width"]), energy=energy, z=0.92)

    branch_count = max(0, round(int(p["lightning.branch_count"]) * energy * span_factor))
    add_lightning_branches(prefix="branch", radius=radius, start_deg=start_angle, arc_deg=arc_angle,
        rotation_deg=rotation, tail_t=tail_t, head_t=head_t, body_width=body_width, material=crack,
        seed=seed * 127 + frame_index * 53, count=branch_count, thickness=thickness,
        width_scale=float(p["lightning.width"]), branch_length=float(p["lightning.length"]),
        jitter=float(p["lightning.jitter"]), spread=float(p["lightning.spread"]),
        edge_bias=float(p["lightning.edge_bias"]), cluster_strength=float(p["lightning.cluster_strength"]), energy=energy, z=0.98)

    secondary_count = max(0, round(int(p["lightning.secondary_branch_count"]) * energy * span_factor))
    add_lightning_branches(prefix="secondary", radius=radius, start_deg=start_angle, arc_deg=arc_angle,
        rotation_deg=rotation, tail_t=tail_t, head_t=head_t, body_width=body_width, material=crack,
        seed=seed * 149 + frame_index * 71, count=secondary_count, thickness=thickness,
        width_scale=float(p["lightning.secondary_width"]), branch_length=float(p["lightning.length"]) * 0.56,
        jitter=float(p["lightning.jitter"]) * 1.16, spread=float(p["lightning.spread"]) * 1.10,
        edge_bias=float(p["lightning.edge_bias"]) * 0.90,
        cluster_strength=min(1.0, float(p["lightning.cluster_strength"]) + 0.12), energy=energy, z=1.01)

    spark_count = max(1, round(int(p["sparks.count"]) * (0.22 + 0.50 * energy + 0.20 * breakup)))
    add_directional_sparks(radius=radius, start_deg=start_angle, arc_deg=arc_angle, rotation_deg=rotation,
        tail_t=tail_t, head_t=head_t, material=crack, seed=seed * 131 + frame_index * 61,
        count=spark_count, thickness=thickness, spark_size=float(p["sparks.size"]),
        spread=float(p["sparks.spread"]), energy=energy, breakup=breakup, z=1.04)

    if breakup > 0.0:
        previous_tail, _, _, _ = motion_window(max(0, frame_index - 1), frames, peak_t)
        fragment_count = round(int(p["fragments.count"]) * (0.20 + 0.80 * breakup))
        add_decay_fragments(radius=radius, start_deg=start_angle, arc_deg=arc_angle, rotation_deg=rotation,
            old_tail_t=previous_tail, tail_t=tail_t, material_a=inner, material_b=crack,
            seed=seed * 137 + frame_index * 67, count=fragment_count,
            size_param=float(p["fragments.size"]), spread_param=float(p["fragments.spread"]), breakup=breakup, z=0.82)

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
