"""Blender-native VFX renderer V7: asymmetric slash spine + organic breakup.

This pass addresses the main Run-144 parity gap: V6 still read as concentric
circular bands. V7 keeps one deterministic canonical slash motion, but warps
its spine, separates outer/inner width envelopes, limits terminal plumes and
uses triangular dissolve patches so F7/F8 break into organic islands instead
of radial ribs.
"""
from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path

import bpy

_V6_PATH = Path(__file__).with_name("native_generate_vfx_v6.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v6", _V6_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load Blender-native V6 renderer")
v6 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v6)
base = v6.base
_base_embed_sources = v6._base_embed_sources


def _raw_spine(radius: float, t: float, p: dict) -> tuple[float, float]:
    """Low-frequency macro-deformed crescent inspired by Run #144.

    The path still has one coherent sweep, but no longer has constant radius or
    linear angular progression. The upper shoulder is flatter, the middle bend
    turns harder, and the lower exit opens along the tangent.
    """
    t = base.clamp01(t)
    # Non-linear progression: linger through upper shoulder, turn harder in the
    # center, then accelerate into the lower exit.
    tw = t + 0.052 * math.sin(math.pi * t) - 0.030 * math.sin(math.tau * t)
    tw += 0.018 * math.sin(math.tau * 2.0 * t + 0.55)
    angle = math.radians(float(p["start_angle"]) + float(p["arc_angle"]) * tw + float(p["rotation"]))

    # Vary radius strongly enough that the eye stops reading a geometric C.
    radial = 1.0
    radial += 0.115 * math.sin(math.tau * (t - 0.12))
    radial += 0.052 * math.sin(math.tau * 2.0 * t + 0.72)
    radial -= 0.070 * math.exp(-((t - 0.54) / 0.16) ** 2)  # tighter central elbow
    radial += 0.070 * math.exp(-((t - 0.83) / 0.13) ** 2)  # lower belly opens

    x = radius * radial * math.cos(angle)
    y = radius * radial * math.sin(angle)
    # Coherent tangent/normal macro bends. These are intentionally asymmetric.
    tx, ty = -math.sin(angle), math.cos(angle)
    nx, ny = math.cos(angle), math.sin(angle)
    tangent_shift = radius * (
        -0.060 * math.exp(-((t - 0.12) / 0.16) ** 2)
        + 0.055 * math.exp(-((t - 0.82) / 0.14) ** 2)
        + 0.024 * math.sin(math.tau * t + 0.2)
    )
    normal_shift = radius * (
        0.040 * math.sin(math.tau * 1.45 * t + 0.35)
        - 0.030 * math.sin(math.tau * 2.7 * t + 0.9)
    )
    x += tx * tangent_shift + nx * normal_shift
    y += ty * tangent_shift + ny * normal_shift

    ox = float(p["shape.offset_x"]) * radius * 3.35
    oy = -float(p["shape.offset_y"]) * radius * 3.35
    return x + ox, y + oy


def point_on_spine(radius: float, t: float, p: dict):
    x, y = _raw_spine(radius, t, p)
    eps = 0.0015
    ta = max(0.0, t - eps); tb = min(1.0, t + eps)
    xa, ya = _raw_spine(radius, ta, p); xb, yb = _raw_spine(radius, tb, p)
    tangent = math.atan2(yb - ya, xb - xa)
    # Existing renderer functions interpret returned angle as the radial normal,
    # with tangent=(-sin(angle), cos(angle)). Rotate derivative accordingly.
    normal_angle = tangent - math.pi * 0.5
    return x, y, normal_angle


def setup_scene(spec: dict):
    scene, layers = v6.setup_scene(spec)
    scene["vfx_renderer"] = "blender-native-v7"
    scene["vfx_shape_model"] = "asymmetric-warped-spine"
    scene["vfx_breakup_model"] = "jittered-triangular-patches"
    return scene, layers


def _macro_width(u: float, side: str, phase: float) -> float:
    """Independent broad envelopes for outer and cutting edges."""
    belly = math.exp(-((u - 0.61) / 0.25) ** 2)
    shoulder = math.exp(-((u - 0.24) / 0.18) ** 2)
    exit_bulge = math.exp(-((u - 0.83) / 0.13) ** 2)
    if side == "outer":
        return 0.72 + 0.50 * belly + 0.18 * shoulder + 0.17 * exit_bulge + 0.10 * math.sin(math.tau * 2.2 * u + phase)
    return 0.68 + 0.22 * belly - 0.12 * shoulder + 0.08 * math.sin(math.tau * 1.7 * u + phase * 0.63)


def _tri_visibility(u: float, v: float, tier: str, p: dict, seed: int, index: int, frames: int, tri: int) -> float:
    vis = v6.cell_visibility(u, v, tier, p, seed, index, frames)
    if vis >= 0.999:
        return vis
    # Break rectangular/radial alignment with a deterministic triangle-local
    # perturbation. It is small enough to preserve shared large holes.
    rng = random.Random(seed * 2147483647 + index * 4099 + tri * 131)
    return base.clamp01(vis + rng.uniform(-0.15, 0.15))


def add_ribbon(name: str, tier: str, p: dict, radius: float, tail: float, head: float,
               material, collection, seed: int, index: int, frames: int, z: float,
               outer_scale: float, inner_scale: float, irregularity: float = 1.0):
    samples = 118
    lanes = 10
    nominal = float(p["thickness"]) * float(p["shape.body_scale"])
    rng = random.Random(seed * 1009 + sum(map(ord, name)))
    phase_a, phase_b = rng.uniform(0, math.tau), rng.uniform(0, math.tau)
    vertices, centers, widths_by_sample = [], [], []
    for i in range(samples):
        u = i / (samples - 1)
        canonical = tail + (head - tail) * u
        x, y, angle = point_on_spine(radius, canonical, p)
        nx, ny = math.cos(angle), math.sin(angle)
        tx, ty = -math.sin(angle), math.cos(angle)
        env = base.smoothstep(u / 0.070) * base.smoothstep((1.0 - u) / 0.050)
        # Low-frequency deformation only; no repeating scalloped teeth.
        center_shift = nominal * (0.14 * math.sin(math.tau * 1.55 * u + phase_a) + 0.05 * math.sin(math.tau * 3.2 * u + phase_b))
        x += nx * center_shift + tx * nominal * 0.035 * math.sin(math.tau * 1.1 * u + phase_b)
        y += ny * center_shift + ty * nominal * 0.035 * math.sin(math.tau * 1.1 * u + phase_b)
        ow = nominal * outer_scale * env * _macro_width(u, "outer", phase_a)
        iw = nominal * inner_scale * env * _macro_width(u, "inner", phase_b)
        ow *= max(0.22, 1.0 + irregularity * 0.075 * math.sin(math.tau * 4.1 * u + phase_b))
        iw *= max(0.22, 1.0 + irregularity * 0.050 * math.sin(math.tau * 3.7 * u + phase_a))
        centers.append((x, y, tx, ty, nx, ny)); widths_by_sample.append((ow, iw))
        for lane in range(lanes + 1):
            v = lane / lanes
            # Slight lane jitter avoids perfectly parallel inner/outer strips.
            lane_jitter = 0.018 * math.sin(i * 0.73 + lane * 1.91 + phase_a) * (ow + iw)
            offset = -iw + (iw + ow) * v + lane_jitter
            vertices.append((x + nx * offset, y + ny * offset, z))

    faces, removed = [], []
    dissolve_seed = v6._dissolve_seed(name, seed)
    tri_id = 0
    for i in range(1, samples):
        u = (i - 0.5) / (samples - 1)
        x0, y0, tx, ty, nx, ny = centers[i]
        ow, iw = widths_by_sample[i]
        for lane in range(lanes):
            a = (i - 1) * (lanes + 1) + lane
            b = i * (lanes + 1) + lane
            # Alternate diagonal and evaluate each triangle independently so
            # late breakup makes torn islands, not perpendicular ribs.
            tris = ((a, a + 1, b + 1), (a, b + 1, b)) if (i + lane) % 2 == 0 else ((a, a + 1, b), (a + 1, b + 1, b))
            for local_tri, tri in enumerate(tris):
                v = base.clamp01((lane + (0.33 if local_tri == 0 else 0.67)) / lanes)
                vis = _tri_visibility(u, v, tier, p, dissolve_seed, index, frames, tri_id)
                if vis < 0.49:
                    lateral = -iw + (iw + ow) * v
                    removed.append((x0 + nx * lateral, y0 + ny * lateral, tx, ty, nx, ny,
                                    max((iw + ow) / lanes * 0.70, radius * 0.0045), 1.0 - vis, tier))
                else:
                    faces.append(tri)
                tri_id += 1
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(vertices, [], faces); mesh.update()
    obj = bpy.data.objects.new(name, mesh); collection.objects.link(obj)
    obj.data.materials.append(material); base.key_visibility(obj, index + 1, frames)
    return removed


def add_flow_bundle(prefix: str, p: dict, radius: float, tail: float, head: float, energy: float,
                    materials, layers, seed: int, index: int, frames: int, breakup: float) -> None:
    """Embedded painterly texture with only a handful of terminal plumes."""
    nominal = float(p["thickness"]) * float(p["shape.body_scale"])
    tier_specs = (
        ("outer", 13, 0.38, 1.95, 0.065, 0.15, materials["outer"], layers["WISPS"]),
        ("body", 17, 0.02, 1.22, 0.075, 0.17, materials["body"], layers["WISPS"]),
        ("inner", 4, -0.28, 0.12, 0.045, 0.085, materials["inner"], layers["CORE"]),
    )
    plume_slots = {("outer", 1), ("outer", 8), ("body", 3), ("body", 12)}
    for tier, count, off_min, off_max, wmin, wmax, material, collection in tier_specs:
        for stroke in range(count):
            window = v6._flow_window(seed, tier, stroke, breakup)
            if window is None:
                continue
            rng = random.Random(seed * 65537 + stroke * 104729 + sum(map(ord, tier)) * 257)
            left, right, opacity = window
            start = max(left, rng.uniform(0.0, 0.18 if tier != "inner" else 0.08))
            end = min(right, rng.uniform(0.80 if tier != "inner" else 0.86, 1.0))
            if end - start < 0.07:
                continue
            offset = rng.uniform(off_min, off_max)
            phase = rng.uniform(0, math.tau); freq = rng.uniform(0.75, 1.75)
            width_factor = rng.uniform(wmin, wmax); width_phase = rng.uniform(0, math.tau)
            points, widths, visibility = [], [], []
            samples = 52
            for s in range(samples):
                local = s / (samples - 1); u = start + (end - start) * local
                canonical = tail + (head - tail) * u
                x, y, angle = point_on_spine(radius, canonical, p)
                nx, ny = math.cos(angle), math.sin(angle); tx, ty = -math.sin(angle), math.cos(angle)
                normal_offset = nominal * (offset + 0.10 * math.sin(math.tau * freq * local + phase) + 0.035 * math.sin(math.tau * 2.4 * local + phase * 0.4))
                x += nx * normal_offset + tx * nominal * 0.025 * math.sin(math.tau * 1.3 * local + phase)
                y += ny * normal_offset + ty * nominal * 0.025 * math.sin(math.tau * 1.3 * local + phase)
                env = base.smoothstep(local / 0.10) * base.smoothstep((1.0 - local) / 0.085)
                widths.append(max(0.0016, nominal * width_factor * env * opacity * (1.0 + 0.22 * math.sin(math.tau * 2.0 * local + width_phase))))
                points.append((x, y))
                vv = base.clamp01((offset - off_min) / max(1e-6, off_max - off_min))
                visibility.append(v6.cell_visibility(u, vv, tier, p, seed, index, frames))

            # Exactly four intended long plumes during powered frames. They use
            # the true warped-spine tangent and gently bend rather than forming
            # the endpoint spaghetti seen in V6.
            if (tier, stroke) in plume_slots and breakup < 0.62 and energy > 0.62:
                extend_end = stroke % 2 == 0
                anchor_idx = -1 if extend_end else 0
                anchor_u = end if extend_end else start
                _, _, nangle = point_on_spine(radius, tail + (head - tail) * anchor_u, p)
                tx, ty = -math.sin(nangle), math.cos(nangle)
                if not extend_end:
                    tx, ty = -tx, -ty
                px, py = -ty, tx
                anchor = points[anchor_idx]
                length = radius * float(p["shape.tongue_length"]) * rng.uniform(0.45, 0.78) * (0.75 + 0.30 * energy)
                rootw = max(widths[anchor_idx], nominal * width_factor * 0.30)
                ext_pts, ext_ws, ext_vis = [], [], []
                bend_sign = -1.0 if stroke % 3 == 0 else 1.0
                for step in range(1, 9):
                    q = step / 8.0
                    bend = bend_sign * math.sin(math.pi * q) * length * 0.075
                    ext_pts.append((anchor[0] + tx * length * q + px * bend, anchor[1] + ty * length * q + py * bend))
                    ext_ws.append(max(0.0013, rootw * ((1.0 - q) ** 1.55)))
                    ext_vis.append(visibility[anchor_idx])
                if extend_end:
                    points += ext_pts; widths += ext_ws; visibility += ext_vis
                else:
                    points = list(reversed(ext_pts)) + points
                    widths = list(reversed(ext_ws)) + widths
                    visibility = list(reversed(ext_vis)) + visibility

            for ci, (pts, ws) in enumerate(v6._curve_chunks(points, widths, visibility, threshold=0.30)):
                z = 0.34 if tier == "outer" else 0.41 if tier == "body" else 0.50
                if tier != "inner":
                    glow = materials["outer_glow"] if tier == "outer" else materials["body_glow"]
                    base.add_curve(f"{prefix}_{tier}_flow_glow_{stroke}_{ci}", pts, [w * 1.8 for w in ws], glow, layers["PLASMA"], z=z - 0.03, frame=index + 1, frames=frames)
                base.add_curve(f"{prefix}_{tier}_flow_{stroke}_{ci}", pts, ws, material, collection, z=z, frame=index + 1, frames=frames)


def add_lightning(prefix: str, p: dict, radius: float, tail: float, head: float, energy: float, breakup: float,
                  materials, layers, seed: int, index: int, frames: int) -> None:
    rng = random.Random(seed * 524287 + index * 12289 + 1877)
    nominal = float(p["thickness"]) * float(p["shape.body_scale"])
    # Lightning supports the plasma rather than defining the silhouette.
    if energy > 0.72 and breakup < 0.82:
        major = 1 if energy < 0.86 else 2
        for bolt, anchor_u in enumerate((0.34, 0.68)[:major]):
            u = base.clamp01(anchor_u + rng.uniform(-0.025, 0.025))
            canonical = tail + (head - tail) * u
            x, y, nangle = point_on_spine(radius, canonical, p)
            nx, ny = math.cos(nangle), math.sin(nangle); tx, ty = -math.sin(nangle), math.cos(nangle)
            root = (x - nx * nominal * 0.18, y - ny * nominal * 0.18)
            mid = (x + nx * nominal * 0.26, y + ny * nominal * 0.26)
            tangent_bias = rng.uniform(-0.42, 0.42)
            dx, dy = nx + tx * tangent_bias, ny + ty * tangent_bias
            length = radius * rng.uniform(0.18, 0.28) * float(p["lightning.length"])
            pts = [root, (x, y), mid]
            ext = v6._free_bolt(mid, (dx, dy), length, rng, segments=5)[1:]
            pts += ext
            widths = v6._bolt_widths(len(pts), nominal * rng.uniform(0.036, 0.055), 0.0012, rng)
            base.add_curve(f"{prefix}_major_glow_{bolt}", pts, [w * 3.0 for w in widths], materials["lightning_glow"], layers["PLASMA"], z=0.73, frame=index + 1, frames=frames)
            base.add_curve(f"{prefix}_major_{bolt}", pts, widths, materials["lightning"], layers["LIGHTNING"], z=0.78, frame=index + 1, frames=frames)
            if len(pts) > 5:
                slot = 4
                prev, nxt = pts[slot - 1], pts[slot + 1]
                a = math.atan2(nxt[1] - prev[1], nxt[0] - prev[0]) + rng.choice((-1, 1)) * rng.uniform(0.60, 0.82)
                child = v6._free_bolt(pts[slot], (math.cos(a), math.sin(a)), length * 0.25, rng, segments=4)
                childw = v6._bolt_widths(len(child), widths[slot] * 0.38, 0.0009, rng)
                base.add_curve(f"{prefix}_branch_{bolt}", child, childw, materials["lightning"], layers["LIGHTNING"], z=0.79, frame=index + 1, frames=frames)

    # Tiny residual electrical memory only; avoid a forest of disconnected lines.
    micro = 2 if breakup < 0.55 else 3
    for m in range(micro):
        u = rng.uniform(0.12, 0.88); canonical = tail + (head - tail) * u
        x, y, nangle = point_on_spine(radius, canonical, p)
        tx, ty = -math.sin(nangle), math.cos(nangle); nx, ny = math.cos(nangle), math.sin(nangle)
        x += nx * nominal * rng.uniform(-0.10, 0.42); y += ny * nominal * rng.uniform(-0.10, 0.42)
        direction = math.atan2(ty + ny * rng.uniform(-0.34, 0.34), tx + nx * rng.uniform(-0.34, 0.34))
        length = radius * rng.uniform(0.018, 0.038)
        pts = [(x, y)]
        for _ in range(3):
            direction += rng.uniform(-0.38, 0.38)
            x += math.cos(direction) * length / 3; y += math.sin(direction) * length / 3; pts.append((x, y))
        base.add_curve(f"{prefix}_micro_{m}", pts, [0.0031, 0.0021, 0.00135, 0.0008], materials["lightning"], layers["LIGHTNING"], z=0.80, frame=index + 1, frames=frames)


def build_frame(spec: dict, index: int, materials: dict, layers: dict) -> None:
    p = spec["params"]; radius = float(p["radius"]); frames = int(spec["frames"]); seed = int(spec["seed"])
    tail, head, energy, breakup = v6.motion_window(index, frames, float(p["timing.peak"]))
    prefix = f"F{index + 1:02d}"; removed = []
    # Broader outer belly, narrow cutting edge. These layers no longer form
    # parallel concentric bands because both spine and width envelopes differ.
    removed += add_ribbon(prefix + "_outer_haze", "body", p, radius, tail, head, materials["outer_glow"], layers["PLASMA"], seed, index, frames, 0.02, 3.05, 0.82, 1.0)
    removed += add_ribbon(prefix + "_outer", "body", p, radius, tail, head, materials["outer"], layers["BODY"], seed, index, frames, 0.08, 2.45, 0.62, 1.0)
    removed += add_ribbon(prefix + "_body", "body", p, radius, tail, head, materials["body"], layers["BODY"], seed + 31, index, frames, 0.14, 1.58, 0.38, 0.88)
    removed += add_ribbon(prefix + "_inner", "inner", p, radius, tail, head, materials["inner"], layers["BODY"], seed + 47, index, frames, 0.28, 0.30, 0.11, 0.62)
    add_flow_bundle(prefix, p, radius, tail, head, energy, materials, layers, seed, index, frames, breakup)
    # Reuse V6 core logic, but it now follows the warped canonical spine.
    v6.add_hot_core(prefix, p, radius, tail, head, energy, materials, layers, seed, index, frames, breakup)
    add_lightning(prefix, p, radius, tail, head, energy, breakup, materials, layers, seed, index, frames)
    v6.add_fragments(prefix, removed, p, materials, layers, radius, seed, index, frames, breakup)


def embed_sources(spec: dict) -> None:
    _base_embed_sources(spec)
    for filename in ("native_generate_vfx_v6.py", "native_generate_vfx_v7.py"):
        try:
            src = bpy.data.texts.new("SOURCE_" + filename)
            src.write(Path(__file__).with_name(filename).read_text(encoding="utf-8"))
        except OSError:
            pass


# V6 functions dynamically call base.point_on_arc, so swapping this one
# primitive also gives the existing hot-core implementation the asymmetric
# spine without duplicating it.
base.point_on_arc = point_on_spine
base.motion_window = v6.motion_window
base.setup_scene = setup_scene
base.make_materials = v6.make_materials
base.add_ribbon = add_ribbon
base.add_fragments = v6.add_fragments
base.build_frame = build_frame
base.embed_sources = embed_sources

if __name__ == "__main__":
    base.main()
