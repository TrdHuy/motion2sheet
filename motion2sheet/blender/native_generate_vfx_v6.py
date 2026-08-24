"""Blender-native VFX renderer V6: Run-144 parity pass.

V6 keeps source.blend authoritative while matching the approved visual language:
deep royal-blue mass, long tangent plasma flows, a thin irregular hot core,
integrated branching lightning and true late breakup instead of shrink/fade.
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
_base_embed_sources = base.embed_sources
_base_setup_scene = base.setup_scene


def motion_window(index: int, frames: int, peak_t: float) -> tuple[float, float, float, float]:
    t = index / max(1, frames - 1)
    if t <= peak_t:
        g = base.smoothstep(t / max(peak_t, 1e-6))
        return 0.075 * g * g, 0.10 + 0.90 * g, 0.55 + 0.45 * g, 0.0
    d = base.smoothstep((t - peak_t) / max(1e-6, 1.0 - peak_t))
    # Preserve a long arc through F8. Local topology, not global shortening,
    # communicates the decay.
    return 0.075 + 0.27 * d, 1.0, 1.0 - 0.70 * d, d


def _constant_mix(node, values: dict[int, float]) -> None:
    for frame, value in values.items():
        node.mix = value
        node.keyframe_insert(data_path="mix", frame=frame)
    action = node.id_data.animation_data.action if node.id_data.animation_data else None
    if action:
        for curve in action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = "CONSTANT"


def setup_scene(spec: dict):
    scene, layers = _base_setup_scene(spec)
    scene.view_settings.view_transform = "Standard"
    try:
        scene.view_settings.look = "None"
    except TypeError:
        pass
    # This scene is emission-only 2D geometry. 24 TAA samples retain clean
    # sprite edges while making contract iteration substantially faster.
    if getattr(scene, "eevee", None) is not None:
        scene.eevee.taa_render_samples = 24

    scene.use_nodes = True
    tree = scene.node_tree
    tree.nodes.clear()
    render = tree.nodes.new("CompositorNodeRLayers")
    render.name = "VFX_RenderLayers"
    aura = tree.nodes.new("CompositorNodeGlare")
    aura.name = "VFX_PlasmaAura"
    aura.glare_type = "FOG_GLOW"
    aura.quality = "HIGH"
    aura.threshold = 0.70
    aura.size = 7
    hot = tree.nodes.new("CompositorNodeGlare")
    hot.name = "VFX_HotCoreAura"
    hot.glare_type = "FOG_GLOW"
    hot.quality = "HIGH"
    hot.threshold = 1.55
    hot.size = 6
    frames = int(spec.get("frames", 8))
    # Run 144 has luminous powered frames but clean holes in F7/F8. Keep glow
    # native and animated off before the breakup tail.
    _constant_mix(aura, {1: -0.45, max(1, frames - 3): -0.45, frames - 1: -1.0, frames: -1.0})
    _constant_mix(hot, {1: -0.66, max(1, frames - 3): -0.66, frames - 1: -1.0, frames: -1.0})
    composite = tree.nodes.new("CompositorNodeComposite")
    composite.name = "VFX_Composite"
    tree.links.new(render.outputs["Image"], aura.inputs["Image"])
    tree.links.new(aura.outputs["Image"], hot.inputs["Image"])
    tree.links.new(hot.outputs["Image"], composite.inputs["Image"])
    scene["vfx_renderer"] = "blender-native-v6"
    scene["vfx_compositor"] = "run144-parity-powered-glow"
    return scene, layers


def make_materials(p: dict) -> dict:
    outer = base.hex_rgba(str(p["colors.outer"]))
    body = base.hex_rgba(str(p["colors.body"]))
    inner = base.hex_rgba(str(p["colors.inner"]))
    core = base.hex_rgba(str(p["colors.core"]))
    lightning = base.hex_rgba(str(p["colors.lightning"]))
    return {
        "outer": base.emission_material("VFX_Outer", outer, 0.82),
        "body": base.emission_material("VFX_Body", body, 0.94),
        "inner": base.emission_material("VFX_Inner", inner, 1.06),
        "core": base.emission_material("VFX_Core", core, 2.65),
        "lightning": base.emission_material("VFX_Lightning", lightning, 3.65),
        "outer_glow": base.emission_material("VFX_OuterGlow", outer, 0.66, 0.20),
        "body_glow": base.emission_material("VFX_BodyGlow", body, 0.75, 0.17),
        "inner_glow": base.emission_material("VFX_InnerGlow", inner, 0.88, 0.14),
        "lightning_glow": base.emission_material("VFX_LightningGlow", lightning, 1.28, 0.14),
    }


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
    edge = max(0.018, float(p["dissolve.edge_softness"]) * 0.44)
    return base.smoothstep((n - progress + edge) / (2.0 * edge))


def _dissolve_seed(name: str, shape_seed: int) -> int:
    if name.endswith("_body"):
        return shape_seed - 31
    if name.endswith("_inner"):
        return shape_seed - 47
    return shape_seed


def add_ribbon(name: str, tier: str, p: dict, radius: float, tail: float, head: float,
               material, collection, seed: int, index: int, frames: int, z: float,
               outer_scale: float, inner_scale: float, irregularity: float = 1.0):
    samples = 142
    lanes = 12
    body_width = float(p["thickness"]) * float(p["shape.body_scale"])
    rng = random.Random(seed * 1009 + index * 97 + sum(map(ord, name)))
    phase_a, phase_b = rng.uniform(0, math.tau), rng.uniform(0, math.tau)
    vertices, faces, removed, centers, widths_by_sample = [], [], [], [], []
    for i in range(samples):
        u = i / (samples - 1)
        canonical = tail + (head - tail) * u
        x, y, angle = base.point_on_arc(radius, canonical, p)
        nx, ny = math.cos(angle), math.sin(angle)
        tx, ty = -math.sin(angle), math.cos(angle)
        envelope = base.smoothstep(u / 0.075) * base.smoothstep((1.0 - u) / 0.055)
        bulge = 0.79 + 0.35 * math.sin(math.pi * u)
        coarse = math.sin(u * math.tau * 2.65 + phase_a) * 0.23 + math.sin(u * math.tau * 5.3 + phase_b) * 0.12
        edge_wave = math.sin(u * math.tau * 13.0 + phase_b * 0.37) * 0.070
        center_shift = body_width * math.sin(u * math.tau * 3.1 + phase_a * 0.5) * 0.12
        x += nx * center_shift; y += ny * center_shift
        ow = body_width * outer_scale * envelope * bulge * max(0.18, 1.0 + irregularity * (coarse + edge_wave))
        iw = body_width * inner_scale * envelope * max(0.18, 1.0 + irregularity * (coarse * 0.34 - edge_wave * 0.30))
        centers.append((x, y, tx, ty, nx, ny)); widths_by_sample.append((ow, iw))
        for lane in range(lanes + 1):
            v = lane / lanes
            offset = -iw + (iw + ow) * v
            vertices.append((x + nx * offset, y + ny * offset, z))
    dissolve_seed = _dissolve_seed(name, seed)
    for i in range(1, samples):
        mid_u = (i - 0.5) / (samples - 1)
        x0, y0, tx, ty, nx, ny = centers[i]
        ow, iw = widths_by_sample[i]
        for lane in range(lanes):
            v = (lane + 0.5) / lanes
            vis = cell_visibility(mid_u, v, tier, p, dissolve_seed, index, frames)
            # Stronger than V5: F7/F8 should lose connected body, not merely
            # acquire holes while remaining a thick crescent.
            if vis < 0.50:
                lateral_offset = -iw + (iw + ow) * v
                removed.append((x0 + nx * lateral_offset, y0 + ny * lateral_offset, tx, ty, nx, ny,
                                max((iw + ow) / lanes, radius * 0.006), 1.0 - vis, tier))
                continue
            a = (i - 1) * (lanes + 1) + lane
            b = i * (lanes + 1) + lane
            faces.append((a, a + 1, b + 1, b))
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(vertices, [], faces); mesh.update()
    obj = bpy.data.objects.new(name, mesh); collection.objects.link(obj)
    obj.data.materials.append(material); base.key_visibility(obj, index + 1, frames)
    return removed


def _flow_window(seed: int, tier: str, stroke: int, breakup: float):
    ranges = {
        "outer": (0.28, 0.94),
        "body": (0.34, 0.98),
        "inner": (0.46, 1.04),
        "core": (0.58, 0.90),
    }
    rng = random.Random(seed * 1000003 + stroke * 7919 + sum(map(ord, tier)) * 97)
    death = rng.uniform(*ranges[tier])
    if breakup <= death:
        return 0.0, 1.0, 1.0
    excess = (breakup - death) / max(0.05, 1.0 - min(0.98, death))
    if excess >= 0.72:
        return None
    center = rng.uniform(0.18, 0.82)
    span = max(0.08, 0.52 * (1.0 - excess))
    return max(0.0, center - span * 0.5), min(1.0, center + span * 0.5), max(0.16, 1.0 - excess * 0.88)


def _curve_chunks(points, widths, visibility, threshold: float = 0.28):
    chunks, pts, ws = [], [], []
    for point, width, vis in zip(points, widths, visibility):
        if vis < threshold:
            if len(pts) >= 2:
                chunks.append((pts, ws))
            pts, ws = [], []
        else:
            pts.append(point); ws.append(max(0.0015, width * (0.42 + 0.58 * vis)))
    if len(pts) >= 2:
        chunks.append((pts, ws))
    return chunks


def add_flow_bundle(prefix: str, p: dict, radius: float, tail: float, head: float, energy: float,
                    materials, layers, seed: int, index: int, frames: int, breakup: float) -> None:
    nominal = float(p["thickness"]) * float(p["shape.body_scale"])
    # More dark/electric-blue streams and fewer cyan streams than V5. This is
    # the principal palette correction toward Run 144 (~70% deep blue at peak).
    tier_specs = (
        ("outer", 22, 0.48, 2.45, 0.070, 0.16, materials["outer"], layers["WISPS"], 0.24, 0.70, 2),
        ("body", 30, 0.04, 1.65, 0.090, 0.20, materials["body"], layers["WISPS"], 0.20, 0.76, 3),
        ("inner", 6, -0.30, 0.18, 0.050, 0.10, materials["inner"], layers["CORE"], 0.10, 0.84, 0),
    )
    for tier, count, off_min, off_max, wmin, wmax, material, collection, start_max, end_min, terminal_every in tier_specs:
        for stroke in range(count):
            window = _flow_window(seed, tier, stroke, breakup)
            if window is None:
                continue
            rng = random.Random(seed * 65537 + stroke * 104729 + sum(map(ord, tier)) * 257 + index * 131)
            start = rng.uniform(0.0, start_max); end = rng.uniform(end_min, 1.0)
            left, right, opacity = window
            start = max(start, left); end = min(end, right)
            if end - start < 0.055:
                continue
            offset = rng.uniform(off_min, off_max)
            wave_amp = rng.uniform(0.040, 0.21 if tier != "inner" else 0.12)
            wave_freq = rng.uniform(0.72, 2.45)
            tangent_wave = rng.uniform(0.015, 0.095)
            phase_a, phase_b = rng.uniform(0, math.tau), rng.uniform(0, math.tau)
            width_factor = rng.uniform(wmin, wmax)
            width_freq, width_phase = rng.uniform(1.2, 3.6), rng.uniform(0, math.tau)
            width_amp = rng.uniform(0.14, 0.32)
            points, widths, visibility = [], [], []
            samples = 60
            for sample in range(samples):
                local = sample / (samples - 1)
                u = start + (end - start) * local
                canonical = tail + (head - tail) * u
                x, y, angle = base.point_on_arc(radius, canonical, p)
                nx, ny = math.cos(angle), math.sin(angle); tx, ty = -math.sin(angle), math.cos(angle)
                normal_offset = nominal * (offset + math.sin(local * math.tau * wave_freq + phase_a) * wave_amp + math.sin(local * math.tau * wave_freq * 0.47 + phase_b) * wave_amp * 0.38)
                tangent_offset = nominal * math.sin(local * math.tau * 1.7 + phase_b) * tangent_wave
                x += nx * normal_offset + tx * tangent_offset; y += ny * normal_offset + ty * tangent_offset
                env = base.smoothstep(local / 0.10) * base.smoothstep((1.0 - local) / 0.09)
                local_width = 1.0 + math.sin(local * math.tau * width_freq + width_phase) * width_amp
                widths.append(max(0.002, nominal * width_factor * local_width * env * opacity))
                points.append((x, y))
                v = base.clamp01((offset - off_min) / max(1e-6, off_max - off_min))
                visibility.append(cell_visibility(u, v, tier, p, seed, index, frames))

            # Run 144 gets much of its 400+ px peak footprint from long tangent
            # tongues. V5 used ~0.1 radius extensions and stayed compact. These
            # are intentionally long, curved and sparse rather than radial combs.
            if terminal_every and stroke % terminal_every == 0 and breakup < 0.68:
                extend_end = (stroke // terminal_every) % 2 == 1
                length = radius * float(p["shape.tongue_length"]) * rng.uniform(0.58, 1.18)
                length *= 0.72 + 0.42 * energy
                steps = 9
                anchor_index = -1 if extend_end else 0
                anchor_u = end if extend_end else start
                _, _, angle = base.point_on_arc(radius, tail + (head - tail) * anchor_u, p)
                tx, ty = -math.sin(angle), math.cos(angle)
                if not extend_end:
                    tx, ty = -tx, -ty
                px, py = -ty, tx
                anchor = points[anchor_index]
                rootw = max(widths[anchor_index], nominal * width_factor * 0.36)
                ext_pts, ext_ws, ext_vis = [], [], []
                bend_phase = rng.uniform(0, math.tau)
                for step in range(1, steps + 1):
                    q = step / steps
                    bend = math.sin(q * math.pi) * length * rng.uniform(-0.11, 0.11)
                    wave = math.sin(q * math.tau * rng.uniform(0.55, 1.05) + bend_phase) * length * 0.025 * (1.0 - q)
                    ext_pts.append((anchor[0] + tx * length * q + px * (bend + wave), anchor[1] + ty * length * q + py * (bend + wave)))
                    ext_ws.append(max(0.0015, rootw * ((1.0 - q) ** 1.42)))
                    ext_vis.append(visibility[anchor_index])
                if extend_end:
                    points += ext_pts; widths += ext_ws; visibility += ext_vis
                else:
                    points = list(reversed(ext_pts)) + points
                    widths = list(reversed(ext_ws)) + widths
                    visibility = list(reversed(ext_vis)) + visibility

            for ci, (pts, ws) in enumerate(_curve_chunks(points, widths, visibility)):
                z = 0.34 if tier == "outer" else 0.41 if tier == "body" else 0.50
                if tier != "inner":
                    glow_mat = materials["outer_glow"] if tier == "outer" else materials["body_glow"]
                    base.add_curve(f"{prefix}_{tier}_flow_glow_{stroke}_{ci}", pts, [w * 2.15 for w in ws], glow_mat, layers["PLASMA"], z=z - 0.03, frame=index + 1, frames=frames)
                base.add_curve(f"{prefix}_{tier}_flow_{stroke}_{ci}", pts, ws, material, collection, z=z, frame=index + 1, frames=frames)


def add_hot_core(prefix: str, p: dict, radius: float, tail: float, head: float, energy: float,
                 materials, layers, seed: int, index: int, frames: int, breakup: float) -> None:
    nominal = float(p["thickness"]) * float(p["shape.body_scale"])
    heat = base.smoothstep((energy - 0.58) / 0.42)
    late = max(0.0, 1.0 - max(0.0, breakup - 0.25) * 1.55)
    if heat <= 0.01 or late <= 0.01 or breakup > 0.90:
        return
    offsets = (-0.43, -0.29, -0.15, -0.01, 0.11)
    width_scales = (0.050, 0.066, 0.052, 0.060, 0.044)
    for stroke, (offset, width_scale) in enumerate(zip(offsets, width_scales)):
        window = _flow_window(seed + index * 131, "core", stroke, breakup)
        if window is None:
            continue
        left, right, opacity = window
        rng = random.Random(seed * 900001 + index * 3571 + stroke * 613 + 17)
        phase_a, phase_b = rng.uniform(0, math.tau), rng.uniform(0, math.tau)
        freq = rng.uniform(1.65, 3.80); amp = rng.uniform(0.045, 0.15)
        points, widths, visibility = [], [], []
        samples = 90
        for i in range(samples):
            u = i / (samples - 1)
            if u < left or u > right:
                continue
            canonical = tail + (head - tail) * (0.028 + 0.944 * u)
            x, y, angle = base.point_on_arc(radius, canonical, p)
            nx, ny = math.cos(angle), math.sin(angle); tx, ty = -math.sin(angle), math.cos(angle)
            local_offset = offset + math.sin(u * math.tau * freq + phase_a) * amp + math.sin(u * math.tau * freq * 0.43 + phase_b) * amp * 0.38
            x += nx * nominal * local_offset + tx * nominal * 0.035 * math.sin(u * math.tau * 4.9 + phase_b)
            y += ny * nominal * local_offset + ty * nominal * 0.035 * math.sin(u * math.tau * 4.9 + phase_b)
            env = max(0.18, base.smoothstep(u / 0.055) * base.smoothstep((1.0 - u) / 0.05))
            modulation = 1.0 + math.sin(u * math.tau * freq + phase_b) * rng.uniform(0.28, 0.52)
            for pinch in (0.24 + stroke * 0.052, 0.54 + stroke * 0.026, 0.76 - stroke * 0.030):
                dist = abs(u - pinch)
                if dist < 0.060:
                    modulation *= 0.16 + 0.84 * (dist / 0.060)
            width = max(0.0015, nominal * width_scale * max(0.11, modulation) * env * opacity * (0.42 + 0.58 * heat) * late)
            points.append((x, y)); widths.append(width)
            visibility.append(cell_visibility(u, 0.16 + stroke * 0.12, "core", p, seed, index, frames))
        for ci, (pts, ws) in enumerate(_curve_chunks(points, widths, visibility, threshold=0.22)):
            base.add_curve(f"{prefix}_core_cyan_glow_{stroke}_{ci}", pts, [w * 3.0 for w in ws], materials["inner_glow"], layers["PLASMA"], z=0.57, frame=index + 1, frames=frames)
            base.add_curve(f"{prefix}_core_white_{stroke}_{ci}", pts, ws, materials["core"], layers["CORE"], z=0.63, frame=index + 1, frames=frames)


def _bolt_widths(count: int, root: float, tip: float, rng: random.Random):
    result, local = [], 1.0
    for i in range(count):
        u = i / max(1, count - 1)
        local = local * 0.72 + rng.uniform(0.72, 1.28) * 0.28
        result.append(max(tip, (tip + (root - tip) * ((1.0 - u) ** 1.35)) * local))
    result[-1] = tip
    return result


def _free_bolt(origin, direction, length: float, rng: random.Random, segments: int = 5):
    dx, dy = direction; norm = max(1e-6, math.hypot(dx, dy)); dx, dy = dx / norm, dy / norm
    angle = math.atan2(dy, dx); x, y = origin; pts = [(x, y)]
    for _ in range(segments):
        angle += rng.uniform(-0.38, 0.38)
        step = length / segments * rng.uniform(0.76, 1.22)
        x += math.cos(angle) * step; y += math.sin(angle) * step; pts.append((x, y))
    return pts


def add_lightning(prefix: str, p: dict, radius: float, tail: float, head: float, energy: float, breakup: float,
                  materials, layers, seed: int, index: int, frames: int) -> None:
    rng = random.Random(seed * 524287 + index * 12289 + 1877)
    nominal = float(p["thickness"]) * float(p["shape.body_scale"])
    if energy >= 0.56 and breakup < 0.88:
        major = max(1, round(2 * (0.86 + 0.14 * energy) * (1.0 - breakup * 0.50)))
        anchors = (0.30, 0.66)
        for bolt in range(major):
            u = anchors[bolt % len(anchors)] + rng.uniform(-0.035, 0.035)
            canonical = tail + (head - tail) * base.clamp01(u)
            x, y, angle = base.point_on_arc(radius, canonical, p)
            nx, ny = math.cos(angle), math.sin(angle); tx, ty = -math.sin(angle), math.cos(angle)
            points = [(x - nx * nominal * 0.22 - tx * nominal * 0.08, y - ny * nominal * 0.22 - ty * nominal * 0.08), (x, y), (x + nx * nominal * 0.48, y + ny * nominal * 0.48)]
            tangent_bias = rng.uniform(-0.72, 0.72)
            dx, dy = nx + tx * tangent_bias, ny + ty * tangent_bias
            norm = max(1e-6, math.hypot(dx, dy)); dx, dy = dx / norm, dy / norm
            direction = math.atan2(dy, dx); x, y = points[-1]
            length = radius * rng.uniform(0.28, 0.43) * float(p["lightning.length"])
            for _ in range(7):
                direction += rng.uniform(-0.42, 0.42) * float(p["lightning.jitter"])
                step = length / 7 * rng.uniform(0.76, 1.24)
                px, py = -math.sin(direction), math.cos(direction)
                x += math.cos(direction) * step + px * step * rng.uniform(-0.20, 0.20)
                y += math.sin(direction) * step + py * step * rng.uniform(-0.20, 0.20)
                points.append((x, y))
            rootw = nominal * rng.uniform(0.043, 0.072); widths = _bolt_widths(len(points), rootw, 0.0014, rng)
            base.add_curve(f"{prefix}_major_glow_{bolt}", points, [w * 3.8 for w in widths], materials["lightning_glow"], layers["PLASMA"], z=0.73, frame=index + 1, frames=frames)
            base.add_curve(f"{prefix}_major_{bolt}", points, widths, materials["lightning"], layers["LIGHTNING"], z=0.78, frame=index + 1, frames=frames)
            slots = [4, 6]; rng.shuffle(slots)
            for branch, slot in enumerate(slots[:1 + (1 if rng.random() < 0.50 else 0)]):
                prev, nxt = points[max(0, slot - 1)], points[min(len(points) - 1, slot + 1)]
                a = math.atan2(nxt[1] - prev[1], nxt[0] - prev[0]) + rng.uniform(0.55, 0.94) * (-1 if rng.random() < 0.5 else 1)
                child = _free_bolt(points[slot], (math.cos(a), math.sin(a)), length * rng.uniform(0.22, 0.36), rng)
                childw = _bolt_widths(len(child), widths[slot] * 0.40, 0.0010, rng)
                base.add_curve(f"{prefix}_branch_{bolt}_{branch}", child, childw, materials["lightning"], layers["LIGHTNING"], z=0.79, frame=index + 1, frames=frames)
    micro = max(3, round((9 * energy + 6 * breakup) * (1.0 - breakup * 0.28)))
    for m in range(micro):
        u = rng.uniform(0.04, 0.96); canonical = tail + (head - tail) * u
        x, y, angle = base.point_on_arc(radius, canonical, p)
        nx, ny = math.cos(angle), math.sin(angle); tx, ty = -math.sin(angle), math.cos(angle)
        x += nx * nominal * rng.uniform(-0.25, 0.65); y += ny * nominal * rng.uniform(-0.25, 0.65)
        if breakup > 0.65:
            x += nx * radius * rng.uniform(-0.06, 0.09); y += ny * radius * rng.uniform(-0.06, 0.09)
        direction = math.atan2(ty + ny * rng.uniform(-0.55, 0.55), tx + nx * rng.uniform(-0.55, 0.55))
        length = radius * rng.uniform(0.022, 0.060) * (0.78 + 0.36 * breakup)
        pts = [(x, y)]
        for _ in range(3):
            direction += rng.uniform(-0.48, 0.48)
            x += math.cos(direction) * length / 3; y += math.sin(direction) * length / 3; pts.append((x, y))
        base.add_curve(f"{prefix}_micro_{m}", pts, [0.0038, 0.0027, 0.0017, 0.0009], materials["lightning"], layers["LIGHTNING"], z=0.80, frame=index + 1, frames=frames)


def add_fragments(prefix: str, removed, p: dict, materials, layers, radius: float,
                  seed: int, index: int, frames: int, breakup: float) -> None:
    progress = base.dissolve_progress(p, index, frames)
    if progress <= 0.0 or not removed:
        return
    rng = random.Random(seed * 49979687 + index * 8191 + 421)
    # F8 in Run 144 is mostly a perforated curved remnant with detached accents,
    # not a cloud of large shards. Reduce fragment area while preserving count.
    count = round(int(p["dissolve.fragment_count"]) * progress * 1.75)
    for frag in range(count):
        x, y, tx, ty, nx, ny, width, erase, tier = removed[rng.randrange(len(removed))]
        sign = -1.0 if rng.random() < 0.44 else 1.0
        radial = radius * (0.062 + 0.155 * progress) * rng.uniform(0.78, 1.72)
        tangent = radius * (0.008 + 0.027 * progress) * rng.uniform(-0.72, 0.50)
        x += nx * radial * sign + tx * tangent; y += ny * radial * sign + ty * tangent
        size = max(radius * 0.0065, radius * float(p["dissolve.fragment_size"]) * rng.uniform(0.11, 0.28))
        tl = size * rng.uniform(0.40, 0.72); nl = size * rng.uniform(0.46, 0.86); jitter = rng.uniform(-0.16, 0.16) * size
        mat = materials["inner"] if tier == "inner" else materials["body"]
        base.add_polygon(f"{prefix}_fragment_{frag}", [
            (x - tx * tl * 0.55 + nx * nl * 0.55, y - ty * tl * 0.55 + ny * nl * 0.55),
            (x + tx * tl * 0.65 + nx * jitter, y + ty * tl * 0.65 + ny * jitter),
            (x + tx * tl * 0.18 - nx * nl * 0.66, y + ty * tl * 0.18 - ny * nl * 0.66),
            (x - tx * tl * 0.43 - nx * nl * 0.15, y - ty * tl * 0.43 - ny * nl * 0.15),
        ], mat, layers["DISSOLVE"], z=0.84, frame=index + 1, frames=frames)
    sparks = round(int(p["dissolve.spark_count"]) * progress * 0.95)
    for s in range(sparks):
        x, y, tx, ty, nx, ny, width, erase, tier = removed[rng.randrange(len(removed))]
        x += nx * radius * rng.uniform(-0.14, 0.14); y += ny * radius * rng.uniform(-0.14, 0.14)
        length = radius * float(p["dissolve.spark_length"]) * progress * rng.uniform(0.20, 0.58)
        angle = rng.uniform(-1.18, 1.18) * float(p["dissolve.fragment_spread"])
        dx = tx * math.cos(angle) - ty * math.sin(angle); dy = tx * math.sin(angle) + ty * math.cos(angle)
        base.add_curve(f"{prefix}_dissolve_spark_{s}", [(x, y), (x + dx * length, y + dy * length)], [0.0028, 0.0009], materials["lightning"], layers["DISSOLVE"], z=0.87, frame=index + 1, frames=frames)


def build_frame(spec: dict, index: int, materials: dict, layers: dict) -> None:
    p = spec["params"]; radius = float(p["radius"]); frames = int(spec["frames"]); seed = int(spec["seed"])
    tail, head, energy, breakup = motion_window(index, frames, float(p["timing.peak"]))
    prefix = f"F{index + 1:02d}"; removed = []
    # Put most occupancy into dark/electric blue; cyan is a narrow hot support.
    removed += add_ribbon(prefix + "_outer_haze", "body", p, radius, tail, head, materials["outer_glow"], layers["PLASMA"], seed, index, frames, 0.02, 3.30, 1.00, 1.22)
    removed += add_ribbon(prefix + "_outer", "body", p, radius, tail, head, materials["outer"], layers["BODY"], seed, index, frames, 0.08, 2.70, 0.76, 1.16)
    removed += add_ribbon(prefix + "_body", "body", p, radius, tail, head, materials["body"], layers["BODY"], seed + 31, index, frames, 0.14, 1.70, 0.48, 1.02)
    removed += add_ribbon(prefix + "_inner", "inner", p, radius, tail, head, materials["inner"], layers["BODY"], seed + 47, index, frames, 0.28, 0.34, 0.15, 0.76)
    add_flow_bundle(prefix, p, radius, tail, head, energy, materials, layers, seed, index, frames, breakup)
    add_hot_core(prefix, p, radius, tail, head, energy, materials, layers, seed, index, frames, breakup)
    add_lightning(prefix, p, radius, tail, head, energy, breakup, materials, layers, seed, index, frames)
    add_fragments(prefix, removed, p, materials, layers, radius, seed, index, frames, breakup)


def embed_sources(spec: dict) -> None:
    _base_embed_sources(spec)
    try:
        src = bpy.data.texts.new("SOURCE_native_generate_vfx_v6.py")
        src.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError:
        pass


base.motion_window = motion_window
base.setup_scene = setup_scene
base.make_materials = make_materials
base.add_ribbon = add_ribbon
base.add_fragments = add_fragments
base.build_frame = build_frame
base.embed_sources = embed_sources
base.main()
