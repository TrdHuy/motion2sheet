"""Blender-native VFX renderer V4: organic breakup plus native compositor bloom."""
from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path

import bpy

_BASE_PATH = Path(__file__).with_name("native_generate_vfx_v2.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v2", _BASE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load Blender-native V2 renderer")
base = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(base)
_base_add_tongues = base.add_tongues
_base_embed_sources = base.embed_sources
_base_setup_scene = base.setup_scene


def setup_scene(spec: dict):
    scene, layers = _base_setup_scene(spec)
    # Native compositor pass. This stays embedded in source.blend, so the blend
    # remains the authoritative visual source while restoring the soft electric
    # halo and white-hot bloom of the approved pre-refactor contract.
    scene.use_nodes = True
    tree = scene.node_tree
    tree.nodes.clear()
    render = tree.nodes.new("CompositorNodeRLayers")
    render.name = "VFX_RenderLayers"
    glow = tree.nodes.new("CompositorNodeGlare")
    glow.name = "VFX_EnergyGlow"
    glow.glare_type = "FOG_GLOW"
    glow.quality = "HIGH"
    glow.threshold = 0.35
    glow.size = 7
    glow.mix = -0.72
    hot = tree.nodes.new("CompositorNodeGlare")
    hot.name = "VFX_HotCoreGlow"
    hot.glare_type = "FOG_GLOW"
    hot.quality = "HIGH"
    hot.threshold = 1.05
    hot.size = 6
    hot.mix = -0.82
    composite = tree.nodes.new("CompositorNodeComposite")
    composite.name = "VFX_Composite"
    tree.links.new(render.outputs["Image"], glow.inputs["Image"])
    tree.links.new(glow.outputs["Image"], hot.inputs["Image"])
    tree.links.new(hot.outputs["Image"], composite.inputs["Image"])
    scene["vfx_compositor"] = "native-dual-fog-glow"
    return scene, layers


def cell_visibility(u: float, v: float, tier: str, p: dict, seed: int, index: int, frames: int) -> float:
    if tier == "core":
        progress = base.dissolve_progress(p, index, frames, core=True) * float(p["dissolve.core_amount"])
    elif tier == "inner":
        progress = base.dissolve_progress(p, index, frames) * float(p["dissolve.inner_amount"])
    else:
        progress = base.dissolve_progress(p, index, frames) * float(p["dissolve.body_amount"])
    if progress <= 0.0:
        return 1.0
    scale = max(0.015, float(p["dissolve.noise_scale"]))
    frequency = max(3.8, 0.72 / scale)
    shared = base.noise01(u, seed * 32452843 + 179, frequency)
    phase = (seed % 997) * 0.017
    lateral = 0.50 + 0.24 * math.sin(u * math.tau * frequency * 0.61 + v * 11.3 + phase)
    lateral += 0.16 * math.sin(u * math.tau * frequency * 1.47 - v * 19.7 + phase * 0.37)
    lateral += 0.10 * math.sin(u * math.tau * 3.1 + v * 31.1 + phase * 0.81)
    n = base.clamp01(shared * 0.52 + base.clamp01(lateral) * 0.48)
    edge = max(0.018, float(p["dissolve.edge_softness"]) * 0.46)
    return base.smoothstep((n - progress + edge) / (2.0 * edge))


def add_ribbon(name: str, tier: str, p: dict, radius: float, tail: float, head: float,
               material, collection, seed: int, index: int, frames: int, z: float,
               outer_scale: float, inner_scale: float, irregularity: float = 1.0):
    samples = 132
    lanes = 10
    body_width = float(p["thickness"]) * float(p["shape.body_scale"])
    rng = random.Random(seed * 1009 + index * 97 + sum(map(ord, name)))
    phase_a, phase_b = rng.uniform(0, math.tau), rng.uniform(0, math.tau)
    vertices = []
    faces = []
    removed = []
    centers = []
    widths_by_sample = []
    for i in range(samples):
        u = i / (samples - 1)
        canonical = tail + (head - tail) * u
        x, y, angle = base.point_on_arc(radius, canonical, p)
        nx, ny = math.cos(angle), math.sin(angle)
        tx, ty = -math.sin(angle), math.cos(angle)
        envelope = base.smoothstep(u / 0.085) * base.smoothstep((1.0 - u) / 0.065)
        bulge = 0.78 + 0.32 * math.sin(math.pi * u)
        coarse = math.sin(u * math.tau * 2.6 + phase_a) * 0.20 + math.sin(u * math.tau * 5.3 + phase_b) * 0.10
        edge_wave = math.sin(u * math.tau * 13.0 + phase_b * 0.37) * 0.055
        center_shift = body_width * math.sin(u * math.tau * 3.1 + phase_a * 0.5) * 0.10
        x += nx * center_shift
        y += ny * center_shift
        ow = body_width * outer_scale * envelope * bulge * max(0.18, 1.0 + irregularity * (coarse + edge_wave))
        iw = body_width * inner_scale * envelope * max(0.18, 1.0 + irregularity * (coarse * 0.33 - edge_wave * 0.35))
        centers.append((x, y, tx, ty, nx, ny))
        widths_by_sample.append((ow, iw))
        for lane in range(lanes + 1):
            v = lane / lanes
            offset = -iw + (iw + ow) * v
            vertices.append((x + nx * offset, y + ny * offset, z))

    for i in range(1, samples):
        mid_u = (i - 0.5) / (samples - 1)
        x0, y0, tx, ty, nx, ny = centers[i]
        ow, iw = widths_by_sample[i]
        for lane in range(lanes):
            v = (lane + 0.5) / lanes
            vis = cell_visibility(mid_u, v, tier, p, seed, index, frames)
            if vis < 0.42:
                lateral_offset = -iw + (iw + ow) * v
                removed.append((x0 + nx * lateral_offset, y0 + ny * lateral_offset, tx, ty, nx, ny,
                                max((iw + ow) / lanes, radius * 0.006), 1.0 - vis, tier))
                continue
            a = (i - 1) * (lanes + 1) + lane
            b = i * (lanes + 1) + lane
            faces.append((a, a + 1, b + 1, b))

    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.data.materials.append(material)
    base.key_visibility(obj, index + 1, frames)
    return removed


def add_tongues(prefix: str, p: dict, radius: float, tail: float, head: float, energy: float, breakup: float,
                materials, layers, seed: int, index: int, frames: int):
    if breakup >= 0.40:
        return
    return _base_add_tongues(prefix, p, radius, tail, head, energy, breakup * 2.0,
                             materials, layers, seed, index, frames)


def add_fragments(prefix: str, removed, p: dict, materials, layers, radius: float,
                  seed: int, index: int, frames: int, breakup: float):
    progress = base.dissolve_progress(p, index, frames)
    if progress <= 0.0 or not removed:
        return
    rng = random.Random(seed * 49979687 + index * 8191 + 421)
    count = round(int(p["dissolve.fragment_count"]) * progress * 1.50)
    for frag in range(count):
        x, y, tx, ty, nx, ny, width, erase, tier = removed[rng.randrange(len(removed))]
        sign = -1.0 if rng.random() < 0.45 else 1.0
        radial = radius * (0.055 + 0.140 * progress) * rng.uniform(0.75, 1.70)
        tangent = radius * (0.006 + 0.025 * progress) * rng.uniform(-0.70, 0.45)
        x += nx * radial * sign + tx * tangent
        y += ny * radial * sign + ty * tangent
        size = max(radius * 0.009, radius * float(p["dissolve.fragment_size"]) * rng.uniform(0.16, 0.42))
        tangent_len = size * rng.uniform(0.45, 0.80)
        normal_len = size * rng.uniform(0.50, 0.95)
        jitter = rng.uniform(-0.18, 0.18) * size
        mat = materials["inner"] if tier == "inner" else materials["core"] if tier == "core" else materials["body"]
        base.add_polygon(
            f"{prefix}_fragment_{frag}",
            [
                (x - tx * tangent_len * 0.55 + nx * normal_len * 0.55, y - ty * tangent_len * 0.55 + ny * normal_len * 0.55),
                (x + tx * tangent_len * 0.65 + nx * jitter, y + ty * tangent_len * 0.65 + ny * jitter),
                (x + tx * tangent_len * 0.20 - nx * normal_len * 0.65, y + ty * tangent_len * 0.20 - ny * normal_len * 0.65),
                (x - tx * tangent_len * 0.45 - nx * normal_len * 0.15, y - ty * tangent_len * 0.45 - ny * normal_len * 0.15),
            ],
            mat, layers["DISSOLVE"], z=0.82, frame=index + 1, frames=frames,
        )
    sparks = round(int(p["dissolve.spark_count"]) * progress * 0.95)
    for s in range(sparks):
        x, y, tx, ty, nx, ny, width, erase, tier = removed[rng.randrange(len(removed))]
        radial = radius * (0.060 + 0.145 * progress) * rng.uniform(-1.0, 1.0)
        x += nx * radial
        y += ny * radial
        length = radius * float(p["dissolve.spark_length"]) * progress * rng.uniform(0.25, 0.75)
        angle = rng.uniform(-1.25, 1.25) * float(p["dissolve.fragment_spread"])
        dx = tx * math.cos(angle) - ty * math.sin(angle)
        dy = tx * math.sin(angle) + ty * math.cos(angle)
        base.add_curve(f"{prefix}_dissolve_spark_{s}", [(x, y), (x + dx * length, y + dy * length)],
                       [0.0030, 0.001], materials["lightning"], layers["DISSOLVE"],
                       z=0.86, frame=index + 1, frames=frames)


def embed_sources(spec: dict) -> None:
    _base_embed_sources(spec)
    try:
        src = bpy.data.texts.new("SOURCE_native_generate_vfx_v4.py")
        src.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError:
        pass


base.setup_scene = setup_scene
base.add_ribbon = add_ribbon
base.add_tongues = add_tongues
base.add_fragments = add_fragments
base.embed_sources = embed_sources
base.main()
