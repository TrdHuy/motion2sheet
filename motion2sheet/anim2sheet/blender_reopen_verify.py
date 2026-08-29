"""Verify that saved key-pose Blender state remains authoritative after reopen.

This script is intentionally diagnostic. It opens the already-saved source.blend
in a fresh Blender process, re-samples evaluated arm joints, measures proxy mesh
segments against their evaluated bones, and projects the evaluated skeleton into
the exact scene camera/render pixels used by the object render.

It writes reopen_debug.json but does not enforce quality thresholds itself;
CI applies those thresholds in verify_keypose_authority.py so the diagnostic
artifact is still available when a contract fails.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


REVIEW_FRAMES = [1, 6, 7, 8]
JOINT_BONES = {
    "leftShoulder": ("LeftUpperArm", "head"),
    "leftElbow": ("LeftUpperArm", "tail"),
    "leftWrist": ("LeftForeArm", "tail"),
    "rightShoulder": ("RightUpperArm", "head"),
    "rightElbow": ("RightUpperArm", "tail"),
    "rightWrist": ("RightForeArm", "tail"),
}
AUTHORED_JOINTS = {
    "leftElbow": "leftElbow",
    "leftWrist": "leftWrist",
    "rightElbow": "rightElbow",
    "rightWrist": "rightWrist",
}
PROXY_SEGMENTS = {
    "Body_LeftUpperArm": "LeftUpperArm",
    "Body_LeftForeArm": "LeftForeArm",
    "Body_RightUpperArm": "RightUpperArm",
    "Body_RightForeArm": "RightForeArm",
    "Review_LeftClavicle": "LeftClavicle",
    "Review_RightClavicle": "RightClavicle",
    "Review_LeftHand": "LeftHand",
    "Review_RightHand": "RightHand",
}
OVERLAY_BONES = [
    "Spine", "Chest", "Neck", "Head",
    "LeftClavicle", "LeftUpperArm", "LeftForeArm", "LeftHand",
    "RightClavicle", "RightUpperArm", "RightForeArm", "RightHand",
    "LeftThigh", "LeftShin", "LeftFoot",
    "RightThigh", "RightShin", "RightFoot",
]


def argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def vec(values) -> list[float]:
    return [round(float(v), 6) for v in values]


def distance(a, b) -> float:
    return round((Vector(a) - Vector(b)).length, 6)


def find_armature():
    values = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if len(values) != 1:
        raise RuntimeError(f"expected exactly one armature after reopen, got {len(values)}")
    return values[0]


def bone_point_world(arm, bone_name: str, endpoint: str) -> Vector:
    bone = arm.pose.bones[bone_name]
    point = bone.head if endpoint == "head" else bone.tail
    return arm.matrix_world @ point


def sample_joint_positions(arm) -> dict[str, list[float]]:
    return {
        name: vec(bone_point_world(arm, bone_name, endpoint))
        for name, (bone_name, endpoint) in JOINT_BONES.items()
    }


def average(points: list[Vector]) -> Vector:
    if not points:
        raise RuntimeError("cannot average empty point set")
    total = Vector((0.0, 0.0, 0.0))
    for point in points:
        total += point
    return total / len(points)


def sample_proxy_segment(obj, arm, bone_name: str, depsgraph) -> dict:
    """Estimate deformed cylinder endpoints from evaluated cap centroids.

    All requested proxy objects are rigid single-bone-weighted cylinders. Their
    original vertices are split into the two rest-space caps using the matching
    rest bone axis. The same vertex indices are then sampled from the evaluated
    Armature-modified mesh, making this a direct deformation check rather than a
    render/image heuristic.
    """
    rest_bone = arm.data.bones[bone_name]
    rest_head = Vector(rest_bone.head_local)
    rest_tail = Vector(rest_bone.tail_local)
    rest_axis = rest_tail - rest_head
    if rest_axis.length < 1e-8:
        raise RuntimeError(f"{bone_name} has zero rest length")
    rest_axis.normalize()
    rest_center = (rest_head + rest_tail) * 0.5

    negative = []
    positive = []
    for vertex in obj.data.vertices:
        projection = (Vector(vertex.co) - rest_center).dot(rest_axis)
        (positive if projection >= 0.0 else negative).append(vertex.index)
    if not negative or not positive:
        raise RuntimeError(f"{obj.name}: could not identify both cylinder caps")

    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        start = average([evaluated.matrix_world @ mesh.vertices[i].co for i in negative])
        end = average([evaluated.matrix_world @ mesh.vertices[i].co for i in positive])
    finally:
        evaluated.to_mesh_clear()

    bone_head = bone_point_world(arm, bone_name, "head")
    bone_tail = bone_point_world(arm, bone_name, "tail")
    direct_error = max((start - bone_head).length, (end - bone_tail).length)
    flipped_error = max((end - bone_head).length, (start - bone_tail).length)
    if flipped_error < direct_error:
        start, end = end, start
        endpoint_error = flipped_error
        flipped = True
    else:
        endpoint_error = direct_error
        flipped = False

    mesh_axis = end - start
    bone_axis = bone_tail - bone_head
    mesh_length = mesh_axis.length
    bone_length = bone_axis.length
    if mesh_length < 1e-8 or bone_length < 1e-8:
        angle = 180.0
    else:
        dot = max(-1.0, min(1.0, float(mesh_axis.normalized().dot(bone_axis.normalized()))))
        angle = math.degrees(math.acos(dot))

    mesh_center = (start + end) * 0.5
    bone_center = (bone_head + bone_tail) * 0.5
    return {
        "object": obj.name,
        "bone": bone_name,
        "missing": False,
        "flippedToMatch": flipped,
        "meshStart": vec(start),
        "meshEnd": vec(end),
        "meshCenter": vec(mesh_center),
        "boneHead": vec(bone_head),
        "boneTail": vec(bone_tail),
        "boneCenter": vec(bone_center),
        "endpointError": round(endpoint_error, 6),
        "centerError": round((mesh_center - bone_center).length, 6),
        "axisAngleDeg": round(angle, 6),
        "lengthError": round(abs(mesh_length - bone_length), 6),
    }


def project_pixel(scene, camera, point: Vector) -> list[float]:
    ndc = world_to_camera_view(scene, camera, point)
    width = float(scene.render.resolution_x * scene.render.resolution_percentage / 100.0)
    height = float(scene.render.resolution_y * scene.render.resolution_percentage / 100.0)
    return [round(ndc.x * width, 3), round((1.0 - ndc.y) * height, 3)]


def projected_bones(scene, arm) -> list[dict]:
    camera = scene.camera
    if camera is None:
        raise RuntimeError("saved scene has no camera")
    rows = []
    for name in OVERLAY_BONES:
        if name not in arm.pose.bones:
            continue
        head = bone_point_world(arm, name, "head")
        tail = bone_point_world(arm, name, "tail")
        rows.append({
            "bone": name,
            "headWorld": vec(head),
            "tailWorld": vec(tail),
            "headPx": project_pixel(scene, camera, head),
            "tailPx": project_pixel(scene, camera, tail),
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--output", required=True)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--pre-debug", required=True)
    args, _ = parser.parse_known_args(argv())

    output = Path(args.output).resolve()
    contract = json.loads(Path(args.contract).read_text(encoding="utf-8"))
    pre_debug = json.loads(Path(args.pre_debug).read_text(encoding="utf-8"))
    pre_by_frame = {int(row["frame"]): row for row in pre_debug["samples"]}
    arm = find_armature()
    scene = bpy.context.scene
    depsgraph = bpy.context.evaluated_depsgraph_get()

    frames = []
    max_pre_post = 0.0
    max_authored_pre = 0.0
    max_authored_post = 0.0
    max_proxy_endpoint = 0.0
    max_proxy_center = 0.0
    max_proxy_angle = 0.0
    max_proxy_length = 0.0

    for frame in REVIEW_FRAMES:
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        post = sample_joint_positions(arm)
        pre = pre_by_frame[frame]["joints"]
        authored_pose = contract["poses"][str(frame)]
        joint_rows = {}
        for name in JOINT_BONES:
            row = {
                "preSave": pre[name],
                "postReopen": post[name],
                "prePostError": distance(pre[name], post[name]),
            }
            max_pre_post = max(max_pre_post, row["prePostError"])
            authored_key = AUTHORED_JOINTS.get(name)
            if authored_key:
                authored = authored_pose[authored_key]
                row["authored"] = authored
                row["authoredPreError"] = distance(authored, pre[name])
                row["authoredPostError"] = distance(authored, post[name])
                max_authored_pre = max(max_authored_pre, row["authoredPreError"])
                max_authored_post = max(max_authored_post, row["authoredPostError"])
            joint_rows[name] = row

        proxy_rows = {}
        for object_name, bone_name in PROXY_SEGMENTS.items():
            obj = bpy.data.objects.get(object_name)
            if obj is None:
                proxy_rows[object_name] = {
                    "object": object_name,
                    "bone": bone_name,
                    "missing": True,
                }
                continue
            row = sample_proxy_segment(obj, arm, bone_name, depsgraph)
            proxy_rows[object_name] = row
            max_proxy_endpoint = max(max_proxy_endpoint, row["endpointError"])
            max_proxy_center = max(max_proxy_center, row["centerError"])
            max_proxy_angle = max(max_proxy_angle, row["axisAngleDeg"])
            max_proxy_length = max(max_proxy_length, row["lengthError"])

        frames.append({
            "frame": frame,
            "joints": joint_rows,
            "proxySegments": proxy_rows,
            "bonePixelSegments": projected_bones(scene, arm),
        })

    result = {
        "mode": "saved-blend-authority-diagnostic",
        "frames": REVIEW_FRAMES,
        "sourceBlend": bpy.data.filepath,
        "renderSize": [
            int(scene.render.resolution_x * scene.render.resolution_percentage / 100),
            int(scene.render.resolution_y * scene.render.resolution_percentage / 100),
        ],
        "summary": {
            "maxPrePostJointError": round(max_pre_post, 6),
            "maxAuthoredPreSaveJointError": round(max_authored_pre, 6),
            "maxAuthoredPostReopenJointError": round(max_authored_post, 6),
            "maxProxyEndpointError": round(max_proxy_endpoint, 6),
            "maxProxyCenterError": round(max_proxy_center, 6),
            "maxProxyAxisAngleDeg": round(max_proxy_angle, 6),
            "maxProxyLengthError": round(max_proxy_length, 6),
        },
        "framesData": frames,
    }
    (output / "reopen_debug.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result["summary"], indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
