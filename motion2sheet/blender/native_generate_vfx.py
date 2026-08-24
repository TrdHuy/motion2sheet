"""Blender-native deterministic standalone VFX renderer.

The generated .blend is the authoritative editable source. Every visual effect
is represented by Blender geometry/materials/animation; no rendered PNG is
modified by an image-space VFX pass afterwards.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

import bpy


def argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args(argv())


def smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def motion_window(index: int, frames: int, peak_t: float) -> tuple[float, float, float, float]:
    t = index / max(frames - 1, 1)
    if t <= peak_t:
        growth = smoothstep(t / max(peak_t, 1e-6))
        return 0.075 * growth * growth, 0.10 + 0.90 * growth, 0.55 + 0.45 * growth, 0.0
    decay = smoothstep((t - peak_t) / max(1e-6, 1.0 - peak_t))
    # Preserve curved motion memory at the end instead of collapsing to a blob.
    return 0.075 + 0.50 * decay, 1.0, 1.0 - 0.86 * decay, decay


def dissolve_progress(params: dict, index: int, frames: int, *, core: bool = False) -> float:
    strength = float(params["dissolve.strength"])
    if strength <= 0.0 or frames < 2:
        return 0.0
    start = float(params["dissolve.start"])
    end = float(params["dissolve.end"])
    if core:
        start = min(end, start + float(params["dissolve.core_delay"]))
    t = index / max(1, frames - 1)
    if t <= start:
        return 0.0
    if t >= end:
        return strength
    return strength * smoothstep((t - start) / max(1e-6, end - start))


def hex_rgba(value: str) -> tuple[float, float, float, float]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4)) + (1.0,)


def emission_material(name: str, color, strength: float, alpha: float = 1.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = color
    emission.inputs["Strength"].default_value = strength
    if alpha >= 0.999:
        mat.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    else:
        transparent = nodes.new("ShaderNodeBsdfTransparent")
        mix = nodes.new("ShaderNodeMixShader")
        mix.inputs[0].default_value = alpha
        mat.node_tree.links.new(transparent.outputs[0], mix.inputs[1])
        mat.node_tree.links.new(emission.outputs[0], mix.inputs[2])
        mat.node_tree.links.new(mix.outputs[0], output.inputs["Surface"])
    return mat


def make_materials(p: dict) -> dict:
    outer = hex_rgba(str(p["colors.outer"]))
    body = hex_rgba(str(p["colors.body"]))
    inner = hex_rgba(str(p["colors.inner"]))
    core = hex_rgba(str(p["colors.core"]))
    lightning = hex_rgba(str(p["colors.lightning"]))
    return {
        "outer": emission_material("VFX_Outer", outer, float(p["intensity.outer"]) * 2.0),
        "body": emission_material("VFX_Body", body, float(p["intensity.body"]) * 2.2),
        "inner": emission_material("VFX_Inner", inner, float(p["intensity.inner"]) * 2.2),
        "core": emission_material("VFX_Core", core, float(p["intensity.core"]) * 1.7),
        "lightning": emission_material("VFX_Lightning", lightning, float(p["intensity.lightning"]) * 1.8),
        "outer_glow": emission_material("VFX_OuterGlow", outer, 1.1, 0.10),
        "body_glow": emission_material("VFX_BodyGlow", body, 1.3, 0.12),
        "inner_glow": emission_material("VFX_InnerGlow", inner, 1.5, 0.14),
        "core_glow": emission_material("VFX_CoreGlow", inner, 1.7, 0.12),
        "lightning_glow": emission_material("VFX_LightningGlow", lightning, 1.9, 0.14),
    }


def clean_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)
    for datablocks in (bpy.data.curves, bpy.data.meshes, bpy.data.materials, bpy.data.cameras):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)


def create_collection(name: str, parent=None):
    collection = bpy.data.collections.new(name)
    if parent is None:
        bpy.context.scene.collection.children.link(collection)
    else:
        parent.children.link(collection)
    return collection


def setup_scene(spec: dict):
    clean_scene()
    scene = bpy.context.scene
    p = spec["params"]
    radius = float(p["radius"])
    canvas = tuple(spec["canvas"])
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = int(canvas[0])
    scene.render.resolution_y = int(canvas[1])
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = True
    scene.render.fps = int(spec["fps"])
    scene.frame_start = 1
    scene.frame_end = int(spec["frames"])
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.world.color = (0.0, 0.0, 0.0)

    camera_data = bpy.data.cameras.new("VFXCamera")
    camera = bpy.data.objects.new("VFXCamera", camera_data)
    scene.collection.objects.link(camera)
    camera.location = (0.0, 0.0, 10.0)
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = radius * 3.35
    scene.camera = camera

    root = create_collection("VFX_ROOT")
    layers = {name: create_collection(f"VFX_{name}", root) for name in (
        "BODY", "CORE", "LIGHTNING", "WISPS", "PLUMES", "PLASMA", "FRAGMENTS", "DISSOLVE"
    )}
    scene["vfx_renderer"] = "blender-native"
    scene["vfx_seed"] = int(spec["seed"])
    return scene, layers


def point_on_arc(radius: float, t: float, p: dict):
    angle = math.radians(float(p["start_angle"]) + float(p["arc_angle"]) * t + float(p["rotation"]))
    x = radius * math.cos(angle) + float(p["shape.offset_x"]) * radius * 3.35
    y = radius * math.sin(angle) - float(p["shape.offset_y"]) * radius * 3.35
    return x, y, angle


def coherent_noise(u: float, seed: int, frequency: float) -> float:
    rng = random.Random(seed)
    phases = [rng.uniform(0.0, math.tau) for _ in range(3)]
    value = (
        math.sin(u * math.tau * frequency + phases[0]) * 0.55
        + math.sin(u * math.tau * frequency * 2.03 + phases[1]) * 0.30
        + math.sin(u * math.tau * frequency * 4.11 + phases[2]) * 0.15
    )
    return 0.5 + 0.5 * value


def dissolve_visibility(u: float, tier: str, stroke: int, p: dict, seed: int, index: int, frames: int) -> float:
    if tier == "core":
        progress = dissolve_progress(p, index, frames, core=True) * float(p["dissolve.core_amount"])
    elif tier == "inner":
        progress = dissolve_progress(p, index, frames) * float(p["dissolve.inner_amount"])
    else:
        progress = dissolve_progress(p, index, frames) * float(p["dissolve.body_amount"])
    if progress <= 0.0:
        return 1.0
    scale = max(0.01, float(p["dissolve.noise_scale"]))
    frequency = max(6.0, 2.2 / scale)
    global_noise = coherent_noise(u, seed * 101 + 17, frequency)
    local_noise = coherent_noise(u, seed * 131 + stroke * 37 + sum(map(ord, tier)), frequency * 1.37)
    noise = global_noise * 0.80 + local_noise * 0.20
    edge = max(0.01, float(p["dissolve.edge_softness"]))
    return smoothstep((noise - (progress - edge)) / (2.0 * edge))


def add_curve(name: str, points, widths, material, collection, *, z: float, frame: int, frames: int):
    if len(points) < 2:
        return None
    curve = bpy.data.curves.new(name + "Curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 1
    curve.bevel_resolution = 2
    curve.bevel_depth = 0.01
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for cp, point, width in zip(spline.points, points, widths):
        cp.co = (point[0], point[1], z, 1.0)
        cp.radius = max(0.02, width / 0.01)
    obj = bpy.data.objects.new(name, curve)
    collection.objects.link(obj)
    obj.data.materials.append(material)
    key_visibility(obj, frame, frames)
    return obj


def add_polygon(name: str, points, material, collection, *, z: float, frame: int, frames: int):
    if len(points) < 3:
        return None
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata([(x, y, z) for x, y in points], [], [tuple(range(len(points)))])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.data.materials.append(material)
    key_visibility(obj, frame, frames)
    return obj


def key_visibility(obj, target_frame: int, frames: int) -> None:
    obj["vfx_frame"] = target_frame
    keyframes = []
    if target_frame > 1:
        keyframes.append((target_frame - 1, True))
    keyframes.append((target_frame, False))
    if target_frame < frames:
        keyframes.append((target_frame + 1, True))
    for frame, hidden in keyframes:
        obj.hide_render = hidden
        obj.hide_viewport = hidden
        obj.keyframe_insert(data_path="hide_render", frame=frame)
        obj.keyframe_insert(data_path="hide_viewport", frame=frame)


def stroke_path(p: dict, radius: float, tail: float, head: float, tier: str, stroke: int, seed: int, index: int, frames: int):
    rng = random.Random(seed * 65537 + stroke * 104729 + index * 7919 + sum(map(ord, tier)) * 257)
    count = 54
    start = rng.uniform(0.0, {"outer": 0.26, "body": 0.20, "inner": 0.14, "core": 0.05}[tier])
    end = rng.uniform({"outer": 0.70, "body": 0.75, "inner": 0.80, "core": 0.88}[tier], 1.0)
    offset_ranges = {"outer": (0.45, 2.05), "body": (0.05, 1.35), "inner": (-0.34, 0.38), "core": (-0.46, -0.10)}
    width_ranges = {"outer": (0.08, 0.18), "body": (0.11, 0.24), "inner": (0.07, 0.16), "core": (0.055, 0.12)}
    offset = rng.uniform(*offset_ranges[tier])
    width_factor = rng.uniform(*width_ranges[tier])
    phase = rng.uniform(0.0, math.tau)
    wave_frequency = rng.uniform(0.9, 2.5)
    points, widths, removed = [], [], []
    for i in range(count):
        local = i / (count - 1)
        if local < start or local > end:
            continue
        u = (local - start) / max(1e-6, end - start)
        canonical = tail + (head - tail) * local
        x, y, angle = point_on_arc(radius, canonical, p)
        nx, ny = math.cos(angle), math.sin(angle)
        tx, ty = -math.sin(angle), math.cos(angle)
        envelope = smoothstep(u / 0.11) * smoothstep((1.0 - u) / 0.10)
        if tier == "core":
            envelope = max(0.30, envelope)
        base_width = float(p["thickness"]) * float(p["shape.body_scale"]) * 0.48
        tier_scale = {"outer": 0.82, "body": 0.72, "inner": 0.46, "core": 0.24}[tier]
        local_width = max(0.002, base_width * tier_scale * width_factor * 5.0 * envelope)
        wobble = math.sin(u * math.tau * wave_frequency + phase) * base_width * 0.18
        x += nx * (offset * base_width + wobble)
        y += ny * (offset * base_width + wobble)
        x += tx * math.sin(u * math.tau * 1.7 + phase * 0.7) * base_width * 0.06
        visible = dissolve_visibility(u, tier, stroke, p, seed, index, frames)
        if visible < 0.12:
            removed.append((x, y, tx, ty, local_width, 1.0 - visible, tier))
            points.append(None)
            widths.append(0.0)
        else:
            points.append((x, y))
            widths.append(local_width * (0.35 + 0.65 * visible))
            if visible < 0.60:
                removed.append((x, y, tx, ty, local_width, 1.0 - visible, tier))
    chunks = []
    cp, cw = [], []
    for point, width in zip(points, widths):
        if point is None:
            if len(cp) >= 2:
                chunks.append((cp, cw))
            cp, cw = [], []
        else:
            cp.append(point)
            cw.append(width)
    if len(cp) >= 2:
        chunks.append((cp, cw))
    return chunks, removed


def add_stroke_tier(prefix: str, tier: str, count: int, p: dict, radius: float, tail: float, head: float,
                    material, glow_material, layers, seed: int, index: int, frames: int, z: float):
    removed = []
    for stroke in range(count):
        chunks, local_removed = stroke_path(p, radius, tail, head, tier, stroke, seed, index, frames)
        removed.extend(local_removed)
        for chunk_index, (points, widths) in enumerate(chunks):
            add_curve(f"{prefix}_{tier}_{stroke:02d}_{chunk_index}", points, widths, material, layers["CORE" if tier == "core" else "BODY"],
                      z=z, frame=index + 1, frames=frames)
            add_curve(f"{prefix}_{tier}_glow_{stroke:02d}_{chunk_index}", points, [w * 2.7 for w in widths], glow_material, layers["PLASMA"],
                      z=z - 0.04, frame=index + 1, frames=frames)
    return removed


def add_lightning(prefix: str, p: dict, radius: float, tail: float, head: float, energy: float, breakup: float,
                  materials, layers, seed: int, index: int, frames: int):
    if energy < 0.56 or breakup > 0.94:
        return
    rng = random.Random(seed * 524287 + index * 12289 + 1877)
    major_count = max(1, round(int(p["lightning.major_count"]) * (0.82 + 0.18 * energy) * (1.0 - breakup * 0.52)))
    for bolt in range(major_count):
        anchor = tail + (head - tail) * ((bolt + 1) / (major_count + 1) + rng.uniform(-0.08, 0.08))
        x, y, angle = point_on_arc(radius, anchor, p)
        nx, ny = math.cos(angle), math.sin(angle)
        tx, ty = -math.sin(angle), math.cos(angle)
        side = -1.0 if bolt % 2 == 0 else 1.0
        x += nx * float(p["thickness"]) * 0.15 * side
        y += ny * float(p["thickness"]) * 0.15 * side
        length = radius * float(p["lightning.length"]) * rng.uniform(0.28, 0.48)
        points = [(x, y)]
        direction = math.atan2(ny * side + ty * rng.uniform(-0.8, 0.8), nx * side + tx * rng.uniform(-0.8, 0.8))
        for step in range(8):
            direction += rng.uniform(-0.42, 0.42) * float(p["lightning.jitter"])
            seg = length / 8 * rng.uniform(0.75, 1.25)
            x += math.cos(direction) * seg
            y += math.sin(direction) * seg
            points.append((x, y))
        base = rng.uniform(float(p["lightning.major_width_min"]), float(p["lightning.major_width_max"])) * 0.0019
        widths = [max(0.002, base * ((1 - i / max(1, len(points)-1)) ** 1.3)) for i in range(len(points))]
        add_curve(f"{prefix}_lightning_{bolt}", points, widths, materials["lightning"], layers["LIGHTNING"], z=0.82, frame=index + 1, frames=frames)
        add_curve(f"{prefix}_lightning_glow_{bolt}", points, [w * 4.0 for w in widths], materials["lightning_glow"], layers["PLASMA"], z=0.78, frame=index + 1, frames=frames)
        root_points = points[:4]
        root_widths = [w * 2.0 for w in widths[:4]]
        add_curve(f"{prefix}_lightning_root_{bolt}", root_points, root_widths, materials["inner"], layers["LIGHTNING"], z=0.80, frame=index + 1, frames=frames)

    micro_count = round(max(6, min(16, int(p["lightning.micro_count"]))) * (1.0 - breakup * 0.62))
    for micro in range(micro_count):
        anchor = rng.uniform(tail + (head-tail)*0.08, head - (head-tail)*0.08)
        x, y, angle = point_on_arc(radius, anchor, p)
        tx, ty = -math.sin(angle), math.cos(angle)
        nx, ny = math.cos(angle), math.sin(angle)
        side = -1.0 if rng.random() < 0.5 else 1.0
        direction = math.atan2(ny * side + ty * rng.uniform(-1.2, 1.2), nx * side + tx * rng.uniform(-1.2, 1.2))
        length = radius * rng.uniform(0.035, 0.085)
        points = [(x, y)]
        for _ in range(4):
            direction += rng.uniform(-0.36, 0.36)
            x += math.cos(direction) * length / 4
            y += math.sin(direction) * length / 4
            points.append((x, y))
        add_curve(f"{prefix}_micro_{micro}", points, [0.004] * len(points), materials["lightning"], layers["LIGHTNING"], z=0.86, frame=index + 1, frames=frames)


def add_wisps_and_plumes(prefix: str, p: dict, radius: float, tail: float, head: float, energy: float, breakup: float,
                         materials, layers, seed: int, index: int, frames: int):
    rng = random.Random(seed * 65539 + index * 2053 + 91)
    for wisp in range(max(3, round(8 * energy * (1.0 - breakup * 0.45)))):
        anchor = rng.uniform(tail, head)
        x, y, angle = point_on_arc(radius, anchor, p)
        tx, ty = -math.sin(angle), math.cos(angle)
        nx, ny = math.cos(angle), math.sin(angle)
        offset = float(p["thickness"]) * rng.uniform(1.0, 2.4)
        x += nx * offset
        y += ny * offset
        length = radius * rng.uniform(0.05, 0.14)
        points = [(x, y), (x - tx * length * 0.5 + nx * length * rng.uniform(-0.2, 0.2), y - ty * length * 0.5 + ny * length * rng.uniform(-0.2, 0.2)),
                  (x - tx * length, y - ty * length)]
        add_curve(f"{prefix}_wisp_{wisp}", points, [0.012, 0.008, 0.002], materials["body"], layers["WISPS"], z=0.24, frame=index + 1, frames=frames)
    for terminal, sign in ((tail, -1.0), (head, 1.0)):
        x, y, angle = point_on_arc(radius, terminal, p)
        tx, ty = -math.sin(angle) * sign, math.cos(angle) * sign
        for plume in range(3):
            length = radius * rng.uniform(0.10, 0.22) * (0.65 + 0.35 * energy)
            nx, ny = math.cos(angle), math.sin(angle)
            points = [(x, y), (x + tx * length * 0.55 + nx * rng.uniform(-0.08, 0.08), y + ty * length * 0.55 + ny * rng.uniform(-0.08, 0.08)),
                      (x + tx * length, y + ty * length)]
            add_curve(f"{prefix}_plume_{int(sign)}_{plume}", points, [0.020, 0.010, 0.002], materials["body"], layers["PLUMES"], z=0.26, frame=index + 1, frames=frames)


def add_fragments(prefix: str, removed, p: dict, materials, layers, radius: float, seed: int, index: int, frames: int, breakup: float):
    rng = random.Random(seed * 49979687 + index * 8191 + 421)
    progress = dissolve_progress(p, index, frames)
    pool = list(removed)
    if pool and progress > 0:
        count = round(int(p["dissolve.fragment_count"]) * progress)
        for frag in range(count):
            x, y, tx, ty, width, erase, tier = pool[rng.randrange(len(pool))]
            nx, ny = -ty, tx
            drift = radius * float(p["dissolve.fragment_drift"]) * progress * rng.uniform(0.25, 1.0)
            x += nx * drift * rng.uniform(-1.0, 1.0) - tx * drift * rng.uniform(0.0, 0.8)
            y += ny * drift * rng.uniform(-1.0, 1.0) - ty * drift * rng.uniform(0.0, 0.8)
            length = radius * float(p["dissolve.fragment_size"]) * rng.uniform(0.20, 0.75)
            half = max(0.002, length * rng.uniform(0.05, 0.16))
            mat = materials["core" if tier == "core" else "inner" if tier == "inner" else "body"]
            add_polygon(f"{prefix}_dissolve_fragment_{frag}", [(x - tx*length*0.2 + nx*half, y - ty*length*0.2 + ny*half),
                                                               (x + tx*length, y + ty*length),
                                                               (x - tx*length*0.15 - nx*half, y - ty*length*0.15 - ny*half)],
                        mat, layers["DISSOLVE"], z=0.92, frame=index + 1, frames=frames)
        spark_count = round(int(p["dissolve.spark_count"]) * progress)
        for spark in range(spark_count):
            x, y, tx, ty, width, erase, tier = pool[rng.randrange(len(pool))]
            length = radius * float(p["dissolve.spark_length"]) * progress * rng.uniform(0.20, 0.80)
            add_curve(f"{prefix}_dissolve_spark_{spark}", [(x, y), (x + tx*length, y + ty*length)], [0.004, 0.001], materials["lightning"], layers["DISSOLVE"], z=0.96, frame=index + 1, frames=frames)
    if breakup > 0:
        count = round(int(p["fragments.count"]) * (0.06 + 0.28 * breakup))
        for frag in range(count):
            t = rng.uniform(0.0, 0.55)
            x, y, angle = point_on_arc(radius, t, p)
            tx, ty = -math.sin(angle), math.cos(angle)
            nx, ny = math.cos(angle), math.sin(angle)
            drift = radius * float(p["fragments.spread"]) * 0.08 * breakup
            x -= tx * drift * rng.uniform(0.2, 1.0)
            y -= ty * drift * rng.uniform(0.2, 1.0)
            x += nx * drift * rng.uniform(-0.5, 0.5)
            y += ny * drift * rng.uniform(-0.5, 0.5)
            size = radius * float(p["fragments.size"]) * rng.uniform(0.04, 0.14)
            add_polygon(f"{prefix}_decay_fragment_{frag}", [(x - tx*size*0.3 + nx*size*0.25, y - ty*size*0.3 + ny*size*0.25),
                                                            (x + tx*size, y + ty*size),
                                                            (x - tx*size*0.2 - nx*size*0.25, y - ty*size*0.2 - ny*size*0.25)],
                        materials["inner" if frag % 3 else "lightning"], layers["FRAGMENTS"], z=0.72, frame=index + 1, frames=frames)


def build_frame(spec: dict, index: int, materials: dict, layers: dict) -> None:
    p = spec["params"]
    radius = float(p["radius"])
    frames = int(spec["frames"])
    seed = int(spec["seed"])
    tail, head, energy, breakup = motion_window(index, frames, float(p["timing.peak"]))
    prefix = f"F{index + 1:02d}"
    body_count = max(24, min(32, int(p["shape.tongue_count"])))
    removed = []
    removed += add_stroke_tier(prefix, "outer", round(body_count * 0.68), p, radius, tail, head, materials["outer"], materials["outer_glow"], layers, seed, index, frames, 0.10)
    removed += add_stroke_tier(prefix, "body", body_count, p, radius, tail, head, materials["body"], materials["body_glow"], layers, seed, index, frames, 0.20)
    removed += add_stroke_tier(prefix, "inner", max(9, round(body_count * 0.34)), p, radius, tail, head, materials["inner"], materials["inner_glow"], layers, seed, index, frames, 0.34)
    removed += add_stroke_tier(prefix, "core", max(4, min(5, int(p["core.streak_count"]))), p, radius, tail, head, materials["core"], materials["core_glow"], layers, seed, index, frames, 0.58)
    add_lightning(prefix, p, radius, tail, head, energy, breakup, materials, layers, seed, index, frames)
    add_wisps_and_plumes(prefix, p, radius, tail, head, energy, breakup, materials, layers, seed, index, frames)
    add_fragments(prefix, removed, p, materials, layers, radius, seed, index, frames, breakup)


def embed_sources(spec: dict) -> None:
    profile = bpy.data.texts.new("VFX_PROFILE_RESOLVED.json")
    profile.write(json.dumps(spec, indent=2) + "\n")
    readme = bpy.data.texts.new("VFX_README.txt")
    readme.write(
        "motion2sheet Blender-native VFX source\n"
        "All visual layers are Blender objects/materials. Scrub F1..Fn on the timeline.\n"
        "Collections under VFX_ROOT separate BODY/CORE/LIGHTNING/WISPS/PLUMES/PLASMA/FRAGMENTS/DISSOLVE.\n"
        "Rendering source.blend requires no image-space VFX post-processing.\n"
    )
    try:
        source = Path(__file__).read_text(encoding="utf-8")
        text = bpy.data.texts.new("SOURCE_native_generate_vfx.py")
        text.write(source)
    except OSError:
        pass


def main() -> None:
    args = parse_args()
    spec_path = Path(args.spec).resolve()
    output_root = Path(args.output).resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if spec.get("template") != "slash" or spec.get("variant") != "lightning":
        raise RuntimeError("Blender-native MVP supports only slash/lightning")
    scene, layers = setup_scene(spec)
    materials = make_materials(spec["params"])
    for index in range(int(spec["frames"])):
        build_frame(spec, index, materials, layers)
    embed_sources(spec)
    scene.frame_set(1)
    output_root.mkdir(parents=True, exist_ok=True)
    blend_path = output_root / "source.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    frames_dir = output_root / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for frame in range(1, int(spec["frames"]) + 1):
        scene.frame_set(frame)
        scene.render.filepath = str(frames_dir / f"{frame:02d}.png")
        bpy.ops.render.render(write_still=True)
    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    print(f"vfx2sheet: Blender-native scene saved -> {blend_path}")
    print(f"vfx2sheet: rendered {spec['frames']} deterministic frame(s) -> {frames_dir}")


if __name__ == "__main__":
    main()
