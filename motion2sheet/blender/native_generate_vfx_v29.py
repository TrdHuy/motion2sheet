"""Blender-native VFX renderer V29: high-resolution organic F6 erosion polish."""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import bpy

_V28_PATH = Path(__file__).with_name("native_generate_vfx_v28.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v28", _V28_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load V28")
v28 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v28)

v27, v23 = v28.v27, v28.v23
v21, v19, v18, v17, v16, v14 = v28.v21, v28.v19, v28.v18, v28.v17, v28.v16, v28.v14
v12, v9, v8, v7, v6, base = v28.v12, v28.v9, v28.v8, v28.v7, v28.v6, v28.base

_ORIG_ADD_RIBBON = v9.add_ribbon
_ORIG_ADD_FRAGMENTS = v8.add_fragments


def setup_scene(spec):
    scene, layers = v28.setup_scene(spec)
    scene["vfx_renderer"] = "blender-native-v29"
    scene["vfx_f6_transition"] = "high-resolution-organic-holes-no-mechanical-debris"
    return scene, layers


def tri_visibility(u, v, tier, p, seed, index, frames, tri):
    if index != frames - 3:
        return v28.tri_visibility(u, v, tier, p, seed, index, frames, tri)
    if tier == "core":
        return 1.0
    import random
    rng = random.Random(seed * 32452843 + 1451)
    count = 3 if tier == "body" else 2
    best = 99.0
    for _ in range(count):
        cu = rng.uniform(.20, .82)
        cv = rng.uniform(.18, .82)
        ru = rng.uniform(.060, .105)
        rv = rng.uniform(.055, .100)
        ang = rng.uniform(-.75, .75)
        ca, sa = math.cos(ang), math.sin(ang)
        du, dv = u - cu, v - cv
        xu = du * ca + dv * sa
        yv = -du * sa + dv * ca
        d = (xu / ru) ** 2 + (yv / rv) ** 2
        phase = rng.uniform(0.0, math.tau)
        edge = .10 * math.sin(math.tau * (3.4 * u + 2.7 * v) + phase)
        edge += .045 * math.sin(math.tau * (7.2 * u - 4.0 * v) + phase * .41)
        best = min(best, d + edge)
    cutoff = .80 if tier == "body" else .55
    return 0.0 if best < cutoff else 1.0


def add_ribbon(name, tier, p, radius, tail, head, material, collection, seed, index, frames, z, outer_scale, inner_scale, irregularity=1.0):
    if index != frames - 3:
        return _ORIG_ADD_RIBBON(name, tier, p, radius, tail, head, material, collection, seed, index, frames, z, outer_scale, inner_scale, irregularity)

    samples, lanes = 176, 20
    nominal = float(p["thickness"]) * float(p["shape.body_scale"])
    import random
    rng = random.Random(seed * 1009 + sum(map(ord, name)))
    phase_a, phase_b = rng.uniform(0, math.tau), rng.uniform(0, math.tau)
    vertices, centers, widths = [], [], []
    for i in range(samples):
        u = i / (samples - 1)
        canonical = tail + (head - tail) * u
        x, y, angle = v16.point_on_spine(radius, canonical, p)
        nx, ny = math.cos(angle), math.sin(angle)
        tx, ty = -math.sin(angle), math.cos(angle)
        env = base.smoothstep(u / .07) * base.smoothstep((1 - u) / .05)
        shift = nominal * (.11 * math.sin(math.tau * 1.45 * u + phase_a) + .045 * math.sin(math.tau * 2.75 * u + phase_b))
        x += nx * shift + tx * nominal * .026 * math.sin(math.tau * 1.2 * u + phase_b)
        y += ny * shift + ty * nominal * .026 * math.sin(math.tau * 1.2 * u + phase_b)
        ow = nominal * outer_scale * env * v9.macro_width(u, "outer", phase_a)
        iw = nominal * inner_scale * env * v9.macro_width(u, "inner", phase_b)
        ow *= max(.25, 1.0 + irregularity * (.055 * math.sin(math.tau * 3.7 * u + phase_b) + .025 * math.sin(math.tau * 7.1 * u + phase_a)))
        iw *= max(.25, 1.0 + irregularity * .035 * math.sin(math.tau * 3.1 * u + phase_a))
        centers.append((x, y, tx, ty, nx, ny)); widths.append((ow, iw))
        for lane in range(lanes + 1):
            vv = lane / lanes
            offset = -iw + (iw + ow) * vv
            vertices.append((x + nx * offset, y + ny * offset, z))

    faces, removed = [], []
    dissolve_seed = v6._dissolve_seed(name, seed)
    tri_id = 0
    for i in range(1, samples):
        u = (i - .5) / (samples - 1)
        x, y, tx, ty, nx, ny = centers[i]
        ow, iw = widths[i]
        for lane in range(lanes):
            a = (i - 1) * (lanes + 1) + lane
            b = i * (lanes + 1) + lane
            tris = ((a, a + 1, b + 1), (a, b + 1, b)) if (i + lane) % 2 == 0 else ((a, a + 1, b), (a + 1, b + 1, b))
            for local_tri, face in enumerate(tris):
                vv = base.clamp01((lane + (.33 if local_tri == 0 else .67)) / lanes)
                vis = tri_visibility(u, vv, tier, p, dissolve_seed, index, frames, tri_id)
                if vis < .50:
                    lateral = -iw + (iw + ow) * vv
                    removed.append((x + nx * lateral, y + ny * lateral, tx, ty, nx, ny, max((iw + ow) / lanes * .68, radius * .0035), 1 - vis, tier))
                else:
                    faces.append(face)
                tri_id += 1

    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(vertices, [], faces); mesh.update()
    obj = bpy.data.objects.new(name, mesh); collection.objects.link(obj)
    obj.data.materials.append(material); base.key_visibility(obj, index + 1, frames)
    return removed


def add_fragments(prefix, removed, p, materials, layers, radius, seed, index, frames, breakup):
    if index == frames - 3:
        return
    return _ORIG_ADD_FRAGMENTS(prefix, removed, p, materials, layers, radius, seed, index, frames, breakup)


def embed_sources(spec):
    v28.embed_sources(spec)
    try:
        text = bpy.data.texts.new("SOURCE_native_generate_vfx_v29.py")
        text.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError:
        pass

v9.tri_visibility = tri_visibility
v9.add_ribbon = add_ribbon
v8.add_fragments = add_fragments
v9.add_ignition = v28.add_ignition
v21.add_lightning = v28.add_lightning
v6.motion_window = v27.motion_window
v18.add_core = v27.add_core
v17._band_polygon = v19._band_polygon
v12.point_on_spine = v16.point_on_spine; v9.point_on_spine = v16.point_on_spine; v8.point_on_spine = v16.point_on_spine; v7.point_on_spine = v16.point_on_spine; base.point_on_arc = v16.point_on_spine
base.setup_scene = setup_scene; base.make_materials = v14.make_materials; base.build_frame = v23.build_frame; base.embed_sources = embed_sources

if __name__ == "__main__":
    base.main()
