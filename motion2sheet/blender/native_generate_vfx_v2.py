"""Blender-native VFX renderer focused on an editable storybook lightning slash.

Every visual layer is authored as Blender geometry/materials and animation.
Rendered PNGs are final visual pixels; the outer CLI only packages them.
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


def clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def smoothstep(v: float) -> float:
    v = clamp01(v)
    return v * v * (3.0 - 2.0 * v)


def motion_window(index: int, frames: int, peak_t: float) -> tuple[float, float, float, float]:
    t = index / max(1, frames - 1)
    if t <= peak_t:
        g = smoothstep(t / max(peak_t, 1e-6))
        return 0.075 * g * g, 0.10 + 0.90 * g, 0.55 + 0.45 * g, 0.0
    d = smoothstep((t - peak_t) / max(1e-6, 1.0 - peak_t))
    # Keep a long curved trajectory alive while the body disintegrates locally.
    return 0.075 + 0.43 * d, 1.0, 1.0 - 0.82 * d, d


def dissolve_progress(p: dict, index: int, frames: int, *, core: bool = False) -> float:
    strength = float(p["dissolve.strength"])
    if strength <= 0.0 or frames < 2:
        return 0.0
    start = float(p["dissolve.start"])
    end = float(p["dissolve.end"])
    if core:
        start = min(end, start + float(p["dissolve.core_delay"]))
    t = index / max(1, frames - 1)
    if t <= start:
        return 0.0
    if t >= end:
        return strength
    return strength * smoothstep((t - start) / max(1e-6, end - start))


def hex_rgba(value: str):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4)) + (1.0,)


def emission_material(name: str, color, strength: float, alpha: float = 1.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = color
    emission.inputs["Strength"].default_value = strength
    if alpha >= 0.999:
        mat.node_tree.links.new(emission.outputs[0], out.inputs[0])
    else:
        transparent = nodes.new("ShaderNodeBsdfTransparent")
        mix = nodes.new("ShaderNodeMixShader")
        mix.inputs[0].default_value = alpha
        mat.node_tree.links.new(transparent.outputs[0], mix.inputs[1])
        mat.node_tree.links.new(emission.outputs[0], mix.inputs[2])
        mat.node_tree.links.new(mix.outputs[0], out.inputs[0])
    return mat


def make_materials(p: dict) -> dict:
    outer = hex_rgba(str(p["colors.outer"]))
    body = hex_rgba(str(p["colors.body"]))
    inner = hex_rgba(str(p["colors.inner"]))
    core = hex_rgba(str(p["colors.core"]))
    lightning = hex_rgba(str(p["colors.lightning"]))
    return {
        "outer": emission_material("VFX_Outer", outer, 0.62),
        "body": emission_material("VFX_Body", body, 0.88),
        "inner": emission_material("VFX_Inner", inner, 1.25),
        "core": emission_material("VFX_Core", core, 3.4),
        "lightning": emission_material("VFX_Lightning", lightning, 3.5),
        "outer_glow": emission_material("VFX_OuterGlow", outer, 0.52, 0.18),
        "body_glow": emission_material("VFX_BodyGlow", body, 0.70, 0.16),
        "inner_glow": emission_material("VFX_InnerGlow", inner, 0.90, 0.14),
        "lightning_glow": emission_material("VFX_LightningGlow", lightning, 1.10, 0.12),
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


def make_collection(name: str, parent=None):
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

    cam_data = bpy.data.cameras.new("VFXCamera")
    cam = bpy.data.objects.new("VFXCamera", cam_data)
    scene.collection.objects.link(cam)
    cam.location = (0.0, 0.0, 10.0)
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = radius * 3.35
    scene.camera = cam

    root = make_collection("VFX_ROOT")
    layers = {name: make_collection(f"VFX_{name}", root) for name in (
        "BODY", "CORE", "LIGHTNING", "WISPS", "PLUMES", "PLASMA", "FRAGMENTS", "DISSOLVE"
    )}
    scene["vfx_renderer"] = "blender-native-v2"
    scene["vfx_seed"] = int(spec["seed"])
    return scene, layers


def key_visibility(obj, target_frame: int, frame_count: int) -> None:
    obj["vfx_frame"] = target_frame
    if target_frame > 1:
        obj.hide_render = True
        obj.hide_viewport = True
        obj.keyframe_insert(data_path="hide_render", frame=target_frame - 1)
        obj.keyframe_insert(data_path="hide_viewport", frame=target_frame - 1)
    obj.hide_render = False
    obj.hide_viewport = False
    obj.keyframe_insert(data_path="hide_render", frame=target_frame)
    obj.keyframe_insert(data_path="hide_viewport", frame=target_frame)
    if target_frame < frame_count:
        obj.hide_render = True
        obj.hide_viewport = True
        obj.keyframe_insert(data_path="hide_render", frame=target_frame + 1)
        obj.keyframe_insert(data_path="hide_viewport", frame=target_frame + 1)


def point_on_arc(radius: float, t: float, p: dict):
    a = math.radians(float(p["start_angle"]) + float(p["arc_angle"]) * t + float(p["rotation"]))
    ox = float(p["shape.offset_x"]) * radius * 3.35
    oy = -float(p["shape.offset_y"]) * radius * 3.35
    return radius * math.cos(a) + ox, radius * math.sin(a) + oy, a


def noise01(u: float, seed: int, frequency: float) -> float:
    rng = random.Random(seed)
    p1, p2, p3, p4 = [rng.uniform(0.0, math.tau) for _ in range(4)]
    v = (
        math.sin(u * math.tau * frequency + p1) * 0.48
        + math.sin(u * math.tau * frequency * 0.47 + p2) * 0.24
        + math.sin(u * math.tau * frequency * 2.03 + p3) * 0.18
        + math.sin(u * math.tau * frequency * 4.09 + p4) * 0.10
    )
    return clamp01(0.50 + v * 0.50)


def dissolve_visibility(canonical_u: float, tier: str, p: dict, seed: int, index: int, frames: int) -> float:
    if tier == "core":
        progress = dissolve_progress(p, index, frames, core=True) * float(p["dissolve.core_amount"])
    elif tier == "inner":
        progress = dissolve_progress(p, index, frames) * float(p["dissolve.inner_amount"])
    else:
        progress = dissolve_progress(p, index, frames) * float(p["dissolve.body_amount"])
    if progress <= 0.0:
        return 1.0
    scale = max(0.015, float(p["dissolve.noise_scale"]))
    frequency = max(3.6, 0.76 / scale)
    n = noise01(canonical_u, seed * 32452843 + 179, frequency)
    # Shared canonical noise punches matching holes through overlapping layers.
    edge = max(0.018, float(p["dissolve.edge_softness"]) * 0.58)
    return smoothstep((n - progress + edge) / (2.0 * edge))


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
    for cp, pt, width in zip(spline.points, points, widths):
        cp.co = (pt[0], pt[1], z, 1.0)
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


def add_ribbon(name: str, tier: str, p: dict, radius: float, tail: float, head: float,
               material, collection, seed: int, index: int, frames: int, z: float,
               outer_scale: float, inner_scale: float, irregularity: float = 1.0):
    samples = 118
    base = float(p["thickness"]) * float(p["shape.body_scale"])
    rng = random.Random(seed * 1009 + index * 97 + sum(map(ord, name)))
    phase_a, phase_b = rng.uniform(0, math.tau), rng.uniform(0, math.tau)
    vertices = []
    faces = []
    removed = []
    for i in range(samples):
        u = i / (samples - 1)
        canonical = tail + (head - tail) * u
        x, y, angle = point_on_arc(radius, canonical, p)
        nx, ny = math.cos(angle), math.sin(angle)
        tx, ty = -math.sin(angle), math.cos(angle)
        envelope = smoothstep(u / 0.085) * smoothstep((1.0 - u) / 0.065)
        bulge = 0.78 + 0.32 * math.sin(math.pi * u)
        coarse = math.sin(u * math.tau * 2.6 + phase_a) * 0.20 + math.sin(u * math.tau * 5.3 + phase_b) * 0.10
        edge = math.sin(u * math.tau * 13.0 + phase_b * 0.37) * 0.055
        center_shift = base * (math.sin(u * math.tau * 3.1 + phase_a * 0.5) * 0.10)
        x += nx * center_shift
        y += ny * center_shift
        ow = base * outer_scale * envelope * bulge * max(0.18, 1.0 + irregularity * (coarse + edge))
        iw = base * inner_scale * envelope * max(0.18, 1.0 + irregularity * (coarse * 0.33 - edge * 0.35))
        visibility = dissolve_visibility(u, tier, p, seed, index, frames)
        if visibility < 0.96:
            removed.append((x, y, tx, ty, nx, ny, max(ow, iw), 1.0 - visibility, tier))
        scale = 0.34 + 0.66 * visibility
        vertices.append((x + nx * ow * scale, y + ny * ow * scale, z))
        vertices.append((x - nx * iw * scale, y - ny * iw * scale, z))
        if i:
            mid_u = (i - 0.5) / (samples - 1)
            if dissolve_visibility(mid_u, tier, p, seed, index, frames) < 0.30:
                continue
            a = 2 * (i - 1)
            faces.append((a, a + 1, 2 * i + 1, 2 * i))
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.data.materials.append(material)
    key_visibility(obj, index + 1, frames)
    return removed


def add_stream_bands(prefix: str, p: dict, radius: float, tail: float, head: float, materials, layers,
                     seed: int, index: int, frames: int):
    rng = random.Random(seed * 65537 + index * 7919 + 443)
    for band in range(12):
        tier = "inner" if band < 7 else "body"
        material = materials["inner"] if tier == "inner" else materials["body"]
        offset = rng.uniform(-0.15, 0.64) * float(p["thickness"])
        width = rng.uniform(0.014, 0.035) if tier == "inner" else rng.uniform(0.022, 0.050)
        points, widths = [], []
        chunks = []
        for i in range(72):
            u = i / 71.0
            canonical = tail + (head - tail) * u
            x, y, angle = point_on_arc(radius, canonical, p)
            nx, ny = math.cos(angle), math.sin(angle)
            tx, ty = -math.sin(angle), math.cos(angle)
            wobble = float(p["thickness"]) * rng.uniform(0.015, 0.035) * math.sin(u * math.tau * rng.uniform(2.2, 5.4) + band)
            x += nx * (offset + wobble)
            y += ny * (offset + wobble)
            x += tx * float(p["thickness"]) * 0.05 * math.sin(u * math.tau * 2.1 + band * 0.7)
            vis = dissolve_visibility(u, tier, p, seed, index, frames)
            env = smoothstep(u / 0.07) * smoothstep((1-u) / 0.06)
            if vis < 0.24:
                if len(points) >= 2:
                    chunks.append((points, widths))
                points, widths = [], []
            else:
                points.append((x, y))
                widths.append(max(0.002, width * env * (0.40 + 0.60 * vis)))
        if len(points) >= 2:
            chunks.append((points, widths))
        for ci, (pts, ws) in enumerate(chunks):
            add_curve(f"{prefix}_stream_{band}_{ci}", pts, ws, material, layers["CORE"], z=0.36 + band*0.002, frame=index+1, frames=frames)


def add_hot_core(prefix: str, p: dict, radius: float, tail: float, head: float, materials, layers,
                 seed: int, index: int, frames: int):
    rng = random.Random(seed * 900001 + index * 3571 + 17)
    streaks = max(4, min(6, int(p["core.streak_count"])))
    for streak in range(streaks):
        points, widths, chunks = [], [], []
        phase = rng.uniform(0, math.tau)
        for i in range(84):
            u = i / 83.0
            canonical = tail + (head-tail) * (0.035 + 0.93*u)
            x, y, angle = point_on_arc(radius, canonical, p)
            nx, ny = math.cos(angle), math.sin(angle)
            tx, ty = -math.sin(angle), math.cos(angle)
            center = -float(p["thickness"]) * (0.16 + streak * 0.045)
            jitter = float(p["thickness"]) * (0.05 + streak*0.006) * math.sin(u * math.tau * (4.0 + 0.37*streak) + phase)
            x += nx * (center + jitter) + tx * float(p["thickness"]) * 0.028 * math.sin(u*math.tau*6.7+phase)
            y += ny * (center + jitter) + ty * float(p["thickness"]) * 0.028 * math.sin(u*math.tau*6.7+phase)
            vis = dissolve_visibility(u, "core", p, seed, index, frames)
            if vis < 0.20:
                if len(points) >= 2:
                    chunks.append((points, widths))
                points, widths = [], []
            else:
                env = max(0.32, smoothstep(u/0.06)*smoothstep((1-u)/0.05))
                local = float(p["thickness"]) * rng.uniform(0.075, 0.135) * env * (0.48 + 0.52*vis)
                points.append((x,y)); widths.append(local)
        if len(points) >= 2:
            chunks.append((points,widths))
        for ci,(pts,ws) in enumerate(chunks):
            add_curve(f"{prefix}_core_{streak}_{ci}", pts, [w*2.8 for w in ws], materials["inner_glow"], layers["PLASMA"], z=0.54, frame=index+1, frames=frames)
            add_curve(f"{prefix}_core_white_{streak}_{ci}", pts, ws, materials["core"], layers["CORE"], z=0.60, frame=index+1, frames=frames)


def add_tongues(prefix: str, p: dict, radius: float, tail: float, head: float, energy: float, breakup: float,
                materials, layers, seed: int, index: int, frames: int):
    rng = random.Random(seed * 109 + index * 43)
    count = max(6, round(int(p["shape.tongue_count"]) * 0.46 * energy * (1.0-breakup*0.32)))
    base = float(p["thickness"]) * float(p["shape.body_scale"])
    for tongue in range(count):
        u = rng.uniform(0.05,0.95)
        if dissolve_visibility(u, "body", p, seed, index, frames) < 0.35:
            continue
        canonical = tail + (head-tail)*u
        x,y,angle = point_on_arc(radius,canonical,p)
        nx,ny = math.cos(angle),math.sin(angle)
        tx,ty = -math.sin(angle),math.cos(angle)
        outward = base * rng.uniform(1.2,2.3)
        x += nx * base * rng.uniform(1.0,1.7)
        y += ny * base * rng.uniform(1.0,1.7)
        backward = base * rng.uniform(-1.0,1.4)
        length = base * rng.uniform(0.55,1.65) * float(p["shape.tongue_length"])
        tip=(x+nx*length-tx*backward,y+ny*length-ty*backward)
        half=base*rng.uniform(0.035,0.10)
        add_polygon(f"{prefix}_tongue_{tongue}",[(x-tx*half,y-ty*half),tip,(x+tx*half,y+ty*half)],materials["body"],layers["WISPS"],z=0.18,frame=index+1,frames=frames)


def add_lightning(prefix: str, p: dict, radius: float, tail: float, head: float, energy: float, breakup: float,
                  materials, layers, seed: int, index: int, frames: int):
    rng = random.Random(seed * 524287 + index * 12289 + 1877)
    if energy < 0.54:
        return
    major = max(1, round(max(2, int(p["lightning.major_count"])) * (1.0-breakup*0.34)))
    for bolt in range(major):
        u = (bolt+1)/(major+1) + rng.uniform(-0.09,0.09)
        if dissolve_visibility(clamp01(u), "inner", p, seed, index, frames) < 0.16 and breakup > 0.35:
            continue
        canonical=tail+(head-tail)*clamp01(u)
        x,y,angle=point_on_arc(radius,canonical,p)
        nx,ny=math.cos(angle),math.sin(angle)
        tx,ty=-math.sin(angle),math.cos(angle)
        side=-1.0 if bolt%2==0 else 1.0
        direction=math.atan2(ny*side+ty*rng.uniform(-0.75,0.75),nx*side+tx*rng.uniform(-0.75,0.75))
        length=radius*float(p["lightning.length"])*rng.uniform(0.18,0.38)*(0.75+0.25*energy)
        pts=[(x,y)]
        for s in range(8):
            direction += rng.uniform(-0.50,0.50)*float(p["lightning.jitter"])
            seg=length/8*rng.uniform(0.72,1.24)
            x += math.cos(direction)*seg; y += math.sin(direction)*seg
            pts.append((x,y))
        base=float(p["thickness"])*rng.uniform(0.035,0.060)
        ws=[max(0.0015,base*((1-i/(len(pts)-1))**1.25)) for i in range(len(pts))]
        add_curve(f"{prefix}_lightning_glow_{bolt}",pts,[w*4.0 for w in ws],materials["lightning_glow"],layers["PLASMA"],z=0.70,frame=index+1,frames=frames)
        add_curve(f"{prefix}_lightning_{bolt}",pts,ws,materials["lightning"],layers["LIGHTNING"],z=0.76,frame=index+1,frames=frames)
    micro=max(5,round(min(18,int(p["lightning.micro_count"]))*energy*(1-breakup*0.45)))
    for m in range(micro):
        u=rng.uniform(0.05,0.95)
        canonical=tail+(head-tail)*u
        x,y,angle=point_on_arc(radius,canonical,p)
        nx,ny=math.cos(angle),math.sin(angle); tx,ty=-math.sin(angle),math.cos(angle)
        side=-1 if rng.random()<0.5 else 1
        direction=math.atan2(ny*side+ty*rng.uniform(-1.3,1.3),nx*side+tx*rng.uniform(-1.3,1.3))
        length=radius*rng.uniform(0.025,0.075)
        pts=[(x,y)]
        for s in range(4):
            direction+=rng.uniform(-0.45,0.45)
            x+=math.cos(direction)*length/4; y+=math.sin(direction)*length/4
            pts.append((x,y))
        add_curve(f"{prefix}_micro_{m}",pts,[0.004,0.003,0.002,0.0015,0.001],materials["lightning"],layers["LIGHTNING"],z=0.78,frame=index+1,frames=frames)


def add_fragments(prefix: str, removed, p: dict, materials, layers, radius: float, seed: int, index: int, frames: int, breakup: float):
    progress=dissolve_progress(p,index,frames)
    if progress<=0 or not removed:
        return
    rng=random.Random(seed*49979687+index*8191+421)
    count=round(int(p["dissolve.fragment_count"])*progress*1.35)
    for frag in range(count):
        x,y,tx,ty,nx,ny,width,erase,tier=removed[rng.randrange(len(removed))]
        drift=radius*float(p["dissolve.fragment_drift"])*progress*rng.uniform(0.35,1.6)
        x += nx*drift*rng.uniform(-1.0,1.0)-tx*drift*rng.uniform(0.1,1.0)
        y += ny*drift*rng.uniform(-1.0,1.0)-ty*drift*rng.uniform(0.1,1.0)
        length=max(radius*0.006,radius*float(p["dissolve.fragment_size"])*rng.uniform(0.20,0.85))
        half=length*rng.uniform(0.06,0.20)
        mat=materials["inner"] if tier=="inner" else materials["core"] if tier=="core" else materials["body"]
        add_polygon(f"{prefix}_fragment_{frag}",[(x-tx*length*0.25+nx*half,y-ty*length*0.25+ny*half),(x+tx*length,y+ty*length),(x-tx*length*0.18-nx*half,y-ty*length*0.18-ny*half)],mat,layers["DISSOLVE"],z=0.82,frame=index+1,frames=frames)
    sparks=round(int(p["dissolve.spark_count"])*progress*1.25)
    for s in range(sparks):
        x,y,tx,ty,nx,ny,width,erase,tier=removed[rng.randrange(len(removed))]
        length=radius*float(p["dissolve.spark_length"])*progress*rng.uniform(0.25,1.15)
        angle=rng.uniform(-0.7,0.7)*float(p["dissolve.fragment_spread"])
        dx=tx*math.cos(angle)-ty*math.sin(angle); dy=tx*math.sin(angle)+ty*math.cos(angle)
        add_curve(f"{prefix}_dissolve_spark_{s}",[(x,y),(x+dx*length,y+dy*length)],[0.004,0.001],materials["lightning"],layers["DISSOLVE"],z=0.86,frame=index+1,frames=frames)


def build_frame(spec: dict,index: int,materials: dict,layers: dict) -> None:
    p=spec["params"]; radius=float(p["radius"]); frames=int(spec["frames"]); seed=int(spec["seed"])
    tail,head,energy,breakup=motion_window(index,frames,float(p["timing.peak"]))
    prefix=f"F{index+1:02d}"
    removed=[]
    # Broad asymmetric plasma mass first, with shared dissolve holes.
    removed += add_ribbon(prefix+"_outer_haze","body",p,radius,tail,head,materials["outer_glow"],layers["PLASMA"],seed,index,frames,0.02,2.65,0.82,1.15)
    removed += add_ribbon(prefix+"_outer","body",p,radius,tail,head,materials["outer"],layers["BODY"],seed,index,frames,0.08,2.05,0.62,1.10)
    removed += add_ribbon(prefix+"_body","body",p,radius,tail,head,materials["body"],layers["BODY"],seed+31,index,frames,0.14,1.48,0.48,0.96)
    removed += add_ribbon(prefix+"_inner","inner",p,radius,tail,head,materials["inner"],layers["BODY"],seed+47,index,frames,0.28,0.72,0.30,0.78)
    add_stream_bands(prefix,p,radius,tail,head,materials,layers,seed,index,frames)
    add_hot_core(prefix,p,radius,tail,head,materials,layers,seed,index,frames)
    add_tongues(prefix,p,radius,tail,head,energy,breakup,materials,layers,seed,index,frames)
    add_lightning(prefix,p,radius,tail,head,energy,breakup,materials,layers,seed,index,frames)
    add_fragments(prefix,removed,p,materials,layers,radius,seed,index,frames,breakup)


def embed_sources(spec: dict) -> None:
    txt=bpy.data.texts.new("VFX_PROFILE_RESOLVED.json"); txt.write(json.dumps(spec,indent=2)+"\n")
    readme=bpy.data.texts.new("VFX_README.txt")
    readme.write("motion2sheet Blender-native VFX source\nAll visual layers are Blender geometry/materials on the F1..Fn timeline.\nNo image-space VFX post-processing is required after rendering.\n")
    try:
        source=Path(__file__).read_text(encoding="utf-8")
        src=bpy.data.texts.new("SOURCE_native_generate_vfx.py"); src.write(source)
    except OSError:
        pass


def main() -> None:
    args=parse_args(); spec_path=Path(args.spec).resolve(); output=Path(args.output).resolve()
    spec=json.loads(spec_path.read_text(encoding="utf-8"))
    if spec.get("template")!="slash" or spec.get("variant")!="lightning":
        raise RuntimeError("Blender-native renderer supports only slash/lightning")
    scene,layers=setup_scene(spec); materials=make_materials(spec["params"])
    for index in range(int(spec["frames"])):
        build_frame(spec,index,materials,layers)
    embed_sources(spec)
    output.mkdir(parents=True,exist_ok=True); blend_path=output/"source.blend"
    scene.frame_set(1); bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    frames_dir=output/"frames"; frames_dir.mkdir(parents=True,exist_ok=True)
    for frame in range(1,int(spec["frames"])+1):
        scene.frame_set(frame); scene.render.filepath=str(frames_dir/f"{frame:02d}.png"); bpy.ops.render.render(write_still=True)
    scene.frame_set(1); bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    print(f"vfx2sheet: Blender-native scene saved -> {blend_path}")
    print(f"vfx2sheet: rendered {spec['frames']} deterministic frame(s) -> {frames_dir}")


if __name__=="__main__":
    main()
