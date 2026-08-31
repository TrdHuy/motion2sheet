"""Render the actual Blender armature for animation and rig inspection."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import bpy
from mathutils import Vector
from motion2sheet.anim2sheet.common.camera.blender import apply_camera_config

SWORD_OBJECTS = {"SwordGrip", "SwordBlade"}


def argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--output", required=True)
    parser.add_argument("--rig-output", required=True)
    parser.add_argument("--frames", default=None)
    parser.add_argument("--skip-rig-docs", action="store_true")
    parser.add_argument("--camera-config", default=None)
    parser.add_argument("--camera-name", default=None)
    return parser.parse_args(argv())


def find_view3d_context():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != "VIEW_3D": continue
            region = next((v for v in area.regions if v.type == "WINDOW"), None)
            if region is not None: return window, area, region, area.spaces.active
    raise RuntimeError("No VIEW_3D area available for Blender viewport rendering")


def find_armature():
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if len(armatures) != 1: raise RuntimeError(f"Expected exactly one armature, found {len(armatures)}")
    return armatures[0]


def prepare_armature(arm):
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH" and obj.name not in SWORD_OBJECTS: obj.hide_set(True)
    bpy.ops.object.select_all(action="DESELECT"); arm.hide_set(False); arm.select_set(True)
    bpy.context.view_layer.objects.active = arm; arm.show_in_front = True
    arm.data.display_type = "BBONE"; arm.data.axes_position = 0.0


def configure_camera(scene, arm, camera_config=None, camera_name=None):
    if camera_config and camera_name:
        config = json.loads(Path(camera_config).read_text(encoding="utf-8"))
        return apply_camera_config(scene, config["cameras"][camera_name])
    bpy.ops.object.camera_add(location=(0.18, -7.5, 2.25))
    camera = bpy.context.object; camera.data.type = "ORTHO"; camera.data.ortho_scale = 3.55
    direction = Vector((0.18, 0, 1.08)) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler(); scene.camera = camera
    return camera


def configure_scene(scene):
    scene.render.engine = "BLENDER_WORKBENCH"; scene.render.film_transparent = True
    scene.display.shading.light = "STUDIO"; scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = False; scene.display.shading.show_cavity = True
    scene.render.image_settings.file_format = "PNG"; scene.render.image_settings.color_mode = "RGBA"


def render_frames(args, arm):
    scene = bpy.context.scene; configure_scene(scene); configure_camera(scene, arm, args.camera_config, args.camera_name)
    frames = [int(v) for v in args.frames.split(",")] if args.frames else list(range(scene.frame_start, scene.frame_end + 1))
    output = Path(args.output); output.mkdir(parents=True, exist_ok=True); prepare_armature(arm)
    window, area, region, space = find_view3d_context()
    for frame in frames:
        scene.frame_set(frame); bpy.context.view_layer.update(); scene.render.filepath = str((output / f"{frame:02d}.png").resolve())
        override = {"window": window, "area": area, "region": region, "space_data": space, "scene": scene}
        with bpy.context.temp_override(**override): bpy.ops.render.opengl(write_still=True, view_context=True)


def main() -> int:
    args = parse_args(); arm = find_armature(); render_frames(args, arm)
    print(f"anim2sheet skeleton viewport OK -> {args.output}", flush=True); return 0


if __name__ == "__main__": raise SystemExit(main())
