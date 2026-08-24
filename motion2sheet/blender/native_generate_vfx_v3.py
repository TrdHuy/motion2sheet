"""Blender-native VFX renderer V3: irregular 2D breakup and detached fragments.

V3 layers targeted refinements on top of V2 while keeping the generated
source.blend fully authoritative and editable.
"""
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
    # Cross-section variation prevents the old full-width rib/fishbone cuts.
    phase = (seed % 997) * 0.017
    lateral = 0.50 + 0.26 * math.sin(u * math.tau * frequency * 0.73 + v * 8.7 + phase)
    lateral += 0.14 * math.sin(u * math.tau * frequency * 1.91 - v * 15.1 + phase * 0.37)
    lateral += 0.10 * math.sin(u * math.tau * 2.3 + v * 23.7 + phase * 0.81)
    lateral = base.clamp01(lateral)
    n = base.clamp01(shared * 0.58 + lateral * 0.42)
    edge = max(0.018, float(p["dissolve.edge_softness"]) * 0.42)
    return base.smoothstep((n - progress + edge) / (2.0 * edge))


def add_ribbon(name: str, tier: str, p: dict, radius: float, tail: float, head: float,
               material, collection, seed: int, index: int, frames: int, z: float,
               outer_scale: float, inner_scale: float, irregularity: float = 1.0):
    samples = 118
    lanes = 6
    base_width = float(p["thickness"]) * float(p["shape.body_scale"])
    rng = random.Random(seed * 1009 + index * 97 + sum(map(ord, name)))
    phase_a, phase_b = rng.uniform(0, math.tau), rng.uniform(0, math.tau)
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []
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
        center_shift = base_width * math.sin(u * math.tau * 3.1 + phase_a * 0.5) * 0.10
        x += nx * center_shift
        y += ny * center_shift
        ow = base_width * outer_scale * envelope * bulge * max(0.18, 1.0 + irregularity * (coarse + edge_wave))
        iw = base_width * inner_scale * envelope * max(0.18, 1.0 + irregularity * (coarse * 0.33 - edge_wave * 0.35))
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
            if vis < 0.46:
                lateral_offset = -iw + (iw + ow) * v
                removed.append((x0 + nx * lateral_offset, y0 + ny * lateral_offset, tx, ty, nx, ny,
                                max((iw + ow) / lanes, radius * 0.008), 1.0 - vis, tier))
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
    # V2 tongues looked like radial ribs late in the dissolve. Preserve them in
    # the powered phase, then hand late-frame breakup over to real fragments.
    if breakup >= 0.52:
        return
    return base.add_tongues(prefix, p, radius, tail, head, energy, breakup * 1.7,
                            materials, layers, seed, index, frames)


def add_fragments(prefix: str, removed, p: dict, materials, layers, radius: float,
                  seed: int, index: int, frames: int, breakup: float):
    progress = base.dissolve_progress(p, index, frames)
    if progress <= 0.0 or not removed:
        return
    rng = random.Random(seed * 49979687 + index * 8191 + 421)
    # Enough genuinely detached geometry to read as disintegration and to make
    # the final frame more fragmented than its dissolve-off baseline.
    count = round(int(p["dissolve.fragment_count"]) * progress * 3.0)
    for frag in range(count):
        x, y, tx, ty, nx, ny, width, erase, tier = removed[rng.randrange(len(removed))]
        sign = -1.0 if rng.random() < 0.42 else 1.0
        radial = radius * (0.018 + 0.085 * progress) * rng.uniform(0.45, 1.55)
        tangent = radius * (0.012 + 0.055 * progress) * rng.uniform(-1.15, 0.70)
        x += nx * radial * sign + tx * tangent
        y += ny * radial * sign + ty * tangent
        length = radius * float(p["dissolve.fragment_size"]) * rng.uniform(0.36, 0.95)
        length = max(length, radius * 0.018)
        half = length * rng.uniform(0.16, 0.34)
        skew = rng.uniform(-0.35, 0.35) * length
        mat = materials["inner"] if tier == "inner" else materials["core"] if tier == "core" else materials["body"]
        base.add_polygon(
            f"{prefix}_fragment_{frag}",
            [
                (x - tx * length * 0.30 + nx * half, y - ty * length * 0.30 + ny * half),
                (x + tx * length + nx * skew, y + ty * length + ny * skew),
                (x + tx * length * 0.12 - nx * half * 0.72, y + ty * length * 0.12 - ny * half * 0.72),
                (x - tx * length * 0.40 - nx * half * 0.30, y - ty * length * 0.40 - ny * half * 0.30),
            ],
            mat, layers["DISSOLVE"], z=0.82, frame=index + 1, frames=frames,
        )
    sparks = round(int(p["dissolve.spark_count"]) * progress * 1.8)
    for s in range(sparks):
        x, y, tx, ty, nx, ny, width, erase, tier = removed[rng.randrange(len(removed))]
        radial = radius * (0.025 + 0.075 * progress) * rng.uniform(-1.0, 1.0)
        x += nx * radial
        y += ny * radial
        length = radius * float(p["dissolve.spark_length"]) * progress * rng.uniform(0.40, 1.30)
        angle = rng.uniform(-0.95, 0.95) * float(p["dissolve.fragment_spread"])
        dx = tx * math.cos(angle) - ty * math.sin(angle)
        dy = tx * math.sin(angle) + ty * math.cos(angle)
        base.add_curve(f"{prefix}_dissolve_spark_{s}", [(x, y), (x + dx * length, y + dy * length)],
                       [0.004, 0.001], materials["lightning"], layers["DISSOLVE"],
                       z=0.86, frame=index + 1, frames=frames)


def embed_sources(spec: dict) -> None:
    base.embed_sources(spec)
    try:
        src = bpy.data.texts.new("SOURCE_native_generate_vfx_v3.py")
        src.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError:
        pass


base.add_ribbon = add_ribbon
base.add_tongues = add_tongues
base.add_fragments = add_fragments
base.embed_sources = embed_sources
base.main()
