from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy


def argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--output", required=True)
    return parser.parse_args(argv())


def find_view3d_context():
    wm = bpy.context.window_manager
    for window in wm.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            if region is not None:
                return window, area, region, area.spaces.active
    raise RuntimeError("No VIEW_3D area available for Blender viewport skeleton rendering")


def prepare_scene():
    scene = bpy.context.scene
    armatures = [obj for obj in scene.objects if obj.type == "ARMATURE"]
    if len(armatures) != 1:
        raise RuntimeError(f"Expected exactly one armature, found {len(armatures)}")
    arm = armatures[0]

    for obj in scene.objects:
        if obj.type == "MESH" and obj.name not in {"SwordGrip", "SwordBlade"}:
            obj.hide_set(True)

    bpy.ops.object.select_all(action="DESELECT")
    arm.hide_set(False)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    arm.show_in_front = True
    arm.data.display_type = "OCTAHEDRAL"
    arm.data.show_names = False
    arm.data.show_axes = False
    return arm


def configure_view(space):
    space.shading.type = "SOLID"
    space.shading.light = "STUDIO"
    space.shading.color_type = "MATERIAL"
    space.shading.show_shadows = False
    space.shading.show_cavity = True
    space.shading.background_type = "VIEWPORT"
    space.shading.background_color = (0.035, 0.035, 0.035)

    overlay = space.overlay
    overlay.show_overlays = True
    overlay.show_floor = False
    overlay.show_axis_x = False
    overlay.show_axis_y = False
    overlay.show_axis_z = False
    overlay.show_relationship_lines = False
    overlay.show_extras = False
    overlay.show_outline_selected = True


def main() -> int:
    args = parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)

    scene = bpy.context.scene
    prepare_scene()
    window, area, region, space = find_view3d_context()
    configure_view(space)

    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.view3d.view_camera()
        for frame in range(scene.frame_start, scene.frame_end + 1):
            scene.frame_set(frame)
            bpy.context.view_layer.update()
            scene.render.filepath = str(output / f"{frame:02d}.png")
            bpy.ops.render.opengl(write_still=True, view_context=True)

    print(f"anim2sheet: Blender viewport skeleton render OK -> {output}")
    bpy.ops.wm.quit_blender()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
