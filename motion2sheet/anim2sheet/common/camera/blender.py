"""Generic Blender camera application and screen-space projection helpers."""
from __future__ import annotations

import math
from typing import Iterable

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


def apply_camera_config(scene, config: dict):
    camera = scene.camera
    if camera is None:
        data = bpy.data.cameras.new("Anim2SheetReviewCamera")
        camera = bpy.data.objects.new("Anim2SheetReviewCamera", data)
        bpy.context.collection.objects.link(camera)
        scene.camera = camera
    camera.location = tuple(float(v) for v in config["position"])
    camera.rotation_mode = "XYZ"
    camera.rotation_euler = tuple(math.radians(float(v)) for v in config["rotationDeg"])
    projection = config["projection"]
    if projection == "orthographic":
        camera.data.type = "ORTHO"
        camera.data.ortho_scale = float(config["orthoScale"])
    elif projection == "perspective":
        camera.data.type = "PERSP"
        camera.data.lens = float(config["focalLengthMm"])
    else:
        raise RuntimeError(f"unsupported camera projection: {projection}")
    bpy.context.view_layer.update()
    return camera


def project_pixel(scene, camera, point: Vector) -> list[float]:
    ndc = world_to_camera_view(scene, camera, point)
    width = float(scene.render.resolution_x * scene.render.resolution_percentage / 100.0)
    height = float(scene.render.resolution_y * scene.render.resolution_percentage / 100.0)
    return [round(ndc.x * width, 3), round((1.0 - ndc.y) * height, 3)]


def bone_point_world(arm, bone_name: str, endpoint: str) -> Vector:
    bone = arm.pose.bones[bone_name]
    point = bone.head if endpoint == "head" else bone.tail
    return arm.matrix_world @ point


def project_named_points(scene, camera, arm, mapping: dict[str, tuple[str, str]]) -> dict:
    return {
        name: project_pixel(scene, camera, bone_point_world(arm, bone, endpoint))
        for name, (bone, endpoint) in mapping.items()
    }


def projected_bones(scene, camera, arm, names: Iterable[str]) -> list[dict]:
    rows = []
    for name in names:
        if name not in arm.pose.bones:
            continue
        head = bone_point_world(arm, name, "head")
        tail = bone_point_world(arm, name, "tail")
        rows.append({
            "bone": name,
            "headWorld": [round(float(v), 6) for v in head],
            "tailWorld": [round(float(v), 6) for v in tail],
            "headPx": project_pixel(scene, camera, head),
            "tailPx": project_pixel(scene, camera, tail),
        })
    return rows
