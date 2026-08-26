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

# Blender uses its own Python environment. Add the repository root so the
# canonical motion package is importable from Blender's bundled Python.
PACKAGE_ROOT = Path(__file__).resolve().parents[3]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from motion2sheet.motion.retarget import load_profile, retarget_frames

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

DIRECTION_YAW_DEGREES = {"down": 0.0, "left": 90.0, "right": -90.0, "up": 180.0}


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
    parser.add_argument("--profile-file", default=None)
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


def activate_animation(armature: bpy.types.Object):
    animation_data = armature.animation_data_create()
    if animation_data.action is not None:
        return animation_data.action
    for track in animation_data.nla_tracks:
        for strip in track.strips:
            if strip.action is not None:
                for other in animation_data.nla_tracks:
                    other.mute = True
                animation_data.action = strip.action
                bpy.context.view_layer.update()
                return strip.action
    candidates = sorted(
        list(bpy.data.actions),
        key=lambda action: float(action.frame_range[1] - action.frame_range[0]),
        reverse=True,
    )
    for action in candidates:
        try:
            animation_data.action = action
            bpy.context.view_layer.update()
            return action
        except (RuntimeError, TypeError):
            continue
    raise RuntimeError("No usable animation action found for armature")


def action_frame_range(armature: bpy.types.Object) -> tuple[float, float]:
    action = activate_animation(armature)
    start, end = action.frame_range
    if end <= start:
        raise RuntimeError(f"Invalid action frame range: {start}..{end}")
    return float(start), float(end)


def sample_times(start: float, end: float, count: int) -> list[float]:
    if count <= 0:
        raise RuntimeError("Frame sample count must be positive")
    duration = end - start
    if duration <= 0:
        raise RuntimeError(f"Invalid animation range: {start}..{end}")
    return [start + duration * (index / count) for index in range(count)]


def evaluated_joint_world(armature: bpy.types.Object, source_name: str) -> Vector:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = armature.evaluated_get(depsgraph)
    pose_bone = evaluated.pose.bones[source_name]
    return evaluated.matrix_world @ pose_bone.matrix.translation


def canonical_basis(scene, armature, bone_map, reference_frame: float):
    base = math.floor(reference_frame)
    scene.frame_set(int(base), subframe=reference_frame - base)
    bpy.context.view_layer.update()
    pelvis = evaluated_joint_world(armature, bone_map["pelvis"])
    head = evaluated_joint_world(armature, bone_map["head"])
    left_hip = evaluated_joint_world(armature, bone_map["left_hip"])
    right_hip = evaluated_joint_world(armature, bone_map["right_hip"])
    right = right_hip - left_hip
    if right.length < 1e-6:
        left_shoulder = evaluated_joint_world(armature, bone_map["left_shoulder"])
        right_shoulder = evaluated_joint_world(armature, bone_map["right_shoulder"])
        right = right_shoulder - left_shoulder
    if right.length < 1e-6:
        raise RuntimeError("Cannot infer character right axis from hips/shoulders")
    right.normalize()
    up_hint = head - pelvis
    up = up_hint - right * up_hint.dot(right)
    if up.length < 1e-6:
        raise RuntimeError("Cannot infer character up axis from head/pelvis")
    up.normalize()
    forward = right.cross(up)
    if forward.length < 1e-6:
        raise RuntimeError("Cannot infer character forward axis")
    forward.normalize()
    return {
        "origin": pelvis.copy(),
        "right": right.copy(),
        "forward": forward.copy(),
        "up": up.copy(),
    }


def to_canonical(point: Vector, basis) -> Vector:
    delta = point - basis["origin"]
    return Vector((delta.dot(basis["right"]), delta.dot(basis["forward"]), delta.dot(basis["up"])))


def rotate_z(point: Vector, degrees: float) -> Vector:
    angle = math.radians(degrees)
    c, s = math.cos(angle), math.sin(angle)
    return Vector((c * point.x - s * point.y, s * point.x + c * point.y, point.z))


def project_orthographic(point: Vector, elevation_degrees: float) -> tuple[float, float]:
    elevation = math.radians(elevation_degrees)
    screen_x = point.x
    screen_y = point.z * math.cos(elevation) - point.y * math.sin(elevation)
    return float(screen_x), float(screen_y)


def sample_canonical_frame(scene, armature, bone_map, basis, frame_value: float) -> dict[str, list[float]]:
    base = math.floor(frame_value)
    scene.frame_set(int(base), subframe=frame_value - base)
    bpy.context.view_layer.update()
    joints: dict[str, list[float]] = {}
    for canonical, source_name in bone_map.items():
        world = evaluated_joint_world(armature, source_name)
        point = to_canonical(world, basis)
        joints[canonical] = [float(point.x), float(point.y), float(point.z)]
    return joints


def project_frame(frame: dict[str, list[float]], yaw: float, elevation: float) -> dict[str, list[float]]:
    joints: dict[str, list[float]] = {}
    for canonical, values in frame.items():
        point = Vector(values)
        rotated = rotate_z(point, yaw)
        joints[canonical] = list(project_orthographic(rotated, elevation))
    return joints


def vector_list(vector: Vector) -> list[float]:
    return [float(vector.x), float(vector.y), float(vector.z)]


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
    scene = bpy.context.scene
    basis = canonical_basis(scene, armature, bone_map, start)
    canonical_frames = [sample_canonical_frame(scene, armature, bone_map, basis, frame_value) for frame_value in times]
    retarget_metadata = {"profile": "source"}
    if args.profile_file:
        profile = load_profile(Path(args.profile_file).resolve())
        canonical_frames, retarget_metadata = retarget_frames(canonical_frames, profile)
        retarget_metadata["segments"] = profile["segments"]
    raw = {
        "source": str(input_path),
        "action": args.action or input_path.stem,
        "frameRange": [start, end],
        "sampleTimes": times,
        "cameraElevation": args.camera_elevation,
        "directions": {},
        "boneMap": bone_map,
        "canonicalBasis": {
            "right": vector_list(basis["right"]),
            "forward": vector_list(basis["forward"]),
            "up": vector_list(basis["up"]),
        },
        "retarget": retarget_metadata,
        "canonicalFrames": canonical_frames,
    }
    for direction in directions:
        yaw = DIRECTION_YAW_DEGREES[direction]
        raw["directions"][direction] = [project_frame(frame, yaw, args.camera_elevation) for frame in canonical_frames]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    print(
        f"motion2sheet: extracted {args.frames} frames for {len(directions)} direction(s) "
        f"from action range {start:.2f}..{end:.2f}; profile={retarget_metadata['profile']} -> {output_path}"
    )


if __name__ == "__main__":
    main()
