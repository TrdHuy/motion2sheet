"""Blender-side motion extractor."""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

import bpy
from mathutils import Vector

CANONICAL_ALIASES = {
    "pelvis": ("hips", "pelvis", "root"),
    "neck": ("neck",),
    "head": ("head",),
    "left_shoulder": ("leftshoulder", "lshoulder", "shoulderl"),
    "left_elbow": ("leftforearm", "leftlowerarm", "lelbow", "forearml"),
    "left_wrist": ("lefthand", "leftwrist", "lwrist", "handl"),
    "right_shoulder": ("rightshoulder", "rshoulder", "shoulderr"),
    "right_elbow": ("rightforearm", "rightlowerarm", "relbow", "forearmr"),
    "right_wrist": ("righthand", "rightwrist", "rwrist", "handr"),
    "left_hip": ("leftupleg", "leftthigh", "lhip", "thighl"),
    "left_knee": ("leftleg", "leftlowerleg", "leftshin", "lknee", "shinl"),
    "left_ankle": ("leftfoot", "leftankle", "lankle", "footl"),
    "right_hip": ("rightupleg", "rightthigh", "rhip", "thighr"),
    "right_knee": ("rightleg", "rightlowerleg", "rightshin", "rknee", "shinr"),
    "right_ankle": ("rightfoot", "rightankle", "rankle", "footr"),
}

DIRECTION_YAW_DEGREES = {"down": 0.0, "left": -90.0, "right": 90.0, "up": 180.0}


def _argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--frames", type=int, default=8)
    parser.add_argument("--directions", default="down")
    parser.add_argument("--camera-elevation", type=float, default=35.0)
    parser.add_argument("--action", default=None)
    return parser.parse_args(_argv())


def clean_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def import_motion(path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path))
    elif suffix == ".bvh":
        bpy.ops.import_anim.bvh(filepath=str(path), target="ARMATURE")
    else:
        raise RuntimeError(f"Unsupported motion format: {suffix}. Supported: .fbx, .bvh")


def normalize_bone_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.split(":")[-1].lower())


def find_armature() -> bpy.types.Object:
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if len(armatures) != 1:
        raise RuntimeError(f"Expected exactly one armature, found {len(armatures)}")
    return armatures[0]


def map_bones(armature: bpy.types.Object) -> dict[str, str]:
    normalized = {normalize_bone_name(bone.name): bone.name for bone in armature.pose.bones}
    result: dict[str, str] = {}
    for canonical, aliases in CANONICAL_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                result[canonical] = normalized[alias]
                break
        if canonical not in result:
            candidates = [original for key, original in normalized.items() if any(key.endswith(alias) for alias in aliases)]
            if len(candidates) == 1:
                result[canonical] = candidates[0]
    missing = [name for name in CANONICAL_ALIASES if name not in result]
    if missing:
        available = ", ".join(bone.name for bone in armature.pose.bones)
        raise RuntimeError(f"Missing canonical bones: {', '.join(missing)}. Available bones: {available}")
    return result


def action_frame_range(armature: bpy.types.Object) -> tuple[float, float]:
    action = armature.animation_data.action if armature.animation_data else None
    if action is not None:
        start, end = action.frame_range
        return float(start), float(end)
    scene = bpy.context.scene
    if scene.frame_end <= scene.frame_start:
        raise RuntimeError("No usable animation frame range found")
    return float(scene.frame_start), float(scene.frame_end)


def sample_times(start: float, end: float, count: int) -> list[float]:
    if count <= 0:
        raise RuntimeError("Frame sample count must be positive")
    duration = end - start
    if duration <= 0:
        raise RuntimeError(f"Invalid animation range: {start}..{end}")
    return [start + duration * (index / count) for index in range(count)]


def rotate_z(point: Vector, degrees: float) -> Vector:
    angle = math.radians(degrees)
    c, s = math.cos(angle), math.sin(angle)
    return Vector((c * point.x - s * point.y, s * point.x + c * point.y, point.z))


def project_orthographic(point: Vector, elevation_degrees: float) -> tuple[float, float]:
    elevation = math.radians(elevation_degrees)
    right = Vector((1.0, 0.0, 0.0))
    up = Vector((0.0, math.sin(elevation), math.cos(elevation)))
    return float(point.dot(right)), float(point.dot(up))


def sample_frame(scene, armature, bone_map, frame_value: float, yaw: float, elevation: float) -> dict:
    base = math.floor(frame_value)
    scene.frame_set(int(base), subframe=frame_value - base)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = armature.evaluated_get(depsgraph)
    joints = {}
    for canonical, source_name in bone_map.items():
        pose_bone = evaluated.pose.bones[source_name]
        world = evaluated.matrix_world @ pose_bone.head
        rotated = rotate_z(world, yaw)
        joints[canonical] = list(project_orthographic(rotated, elevation))
    return joints


def main() -> None:
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    directions = [item.strip().lower() for item in args.directions.split(",") if item.strip()]
    unknown = [direction for direction in directions if direction not in DIRECTION_YAW_DEGREES]
    if unknown:
        raise RuntimeError(f"Unknown directions: {', '.join(unknown)}")

    clean_scene()
    import_motion(input_path)
    armature = find_armature()
    bone_map = map_bones(armature)
    start, end = action_frame_range(armature)
    times = sample_times(start, end, args.frames)

    raw = {
        "source": str(input_path),
        "action": args.action or input_path.stem,
        "frameRange": [start, end],
        "sampleTimes": times,
        "cameraElevation": args.camera_elevation,
        "directions": {},
        "boneMap": bone_map,
    }
    scene = bpy.context.scene
    for direction in directions:
        yaw = DIRECTION_YAW_DEGREES[direction]
        raw["directions"][direction] = [
            sample_frame(scene, armature, bone_map, frame_value, yaw, args.camera_elevation)
            for frame_value in times
        ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    print(f"motion2sheet: extracted {args.frames} frames for {len(directions)} direction(s) -> {output_path}")


if __name__ == "__main__":
    main()
