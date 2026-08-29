"""Render the actual Blender armature for animation and default-rig inspection.

Animated skeleton frames use Blender Viewport Render (``bpy.ops.render.opengl``).
Blender intentionally omits some text overlays, including bone names, from
Viewport Render. The labeled default-rig diagnostic therefore uses Blender's
own editor screenshot operator (``bpy.ops.screen.screenshot_area``) so the
image contains the exact bone-name labels visible in the 3D Viewport.

No bones or labels are re-drawn with Pillow, ImageDraw, proxy meshes, or an
external renderer.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy


SWORD_OBJECTS = {"SwordGrip", "SwordBlade"}


def argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--output", required=True)
    parser.add_argument("--rig-output", required=True)
    return parser.parse_args(argv())


def find_view3d_context():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            region = next((value for value in area.regions if value.type == "WINDOW"), None)
            if region is not None:
                return window, area, region, area.spaces.active
    raise RuntimeError("No VIEW_3D area available for Blender viewport rendering")


def find_armature():
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if len(armatures) != 1:
        raise RuntimeError(f"Expected exactly one armature, found {len(armatures)}")
    return armatures[0]


def prepare_armature(arm):
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH" and obj.name not in SWORD_OBJECTS:
            obj.hide_set(True)

    bpy.ops.object.select_all(action="DESELECT")
    arm.hide_set(False)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    arm.show_in_front = True
    arm.data.display_type = "OCTAHEDRAL"
    arm.data.show_names = False
    arm.data.show_axes = False


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
    if hasattr(overlay, "show_text"):
        overlay.show_text = True

    # Keep the diagnostic editor screenshot focused on the rig.
    if hasattr(space, "show_region_toolbar"):
        space.show_region_toolbar = False
    if hasattr(space, "show_region_ui"):
        space.show_region_ui = False
    if hasattr(space, "show_region_tool_header"):
        space.show_region_tool_header = False


def set_sword_visible(visible: bool):
    for name in SWORD_OBJECTS:
        obj = bpy.data.objects.get(name)
        if obj is not None:
            obj.hide_set(not visible)


def write_rig_manifest(arm, root: Path):
    bones = []
    for bone in arm.data.bones:
        bones.append({
            "name": bone.name,
            "parent": bone.parent.name if bone.parent else None,
            "connected": bool(bone.use_connect),
            "deform": bool(bone.use_deform),
            "headLocal": [round(float(value), 6) for value in bone.head_local],
            "tailLocal": [round(float(value), 6) for value in bone.tail_local],
        })

    payload = {
        "armature": arm.name,
        "objectRoot": arm.parent.name if arm.parent else None,
        "displayType": arm.data.display_type,
        "boneCount": len(bones),
        "bones": bones,
    }
    (root / "rig_bones.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )

    children = {bone.name: [] for bone in arm.data.bones}
    roots = []
    for bone in arm.data.bones:
        if bone.parent is None:
            roots.append(bone.name)
        else:
            children[bone.parent.name].append(bone.name)
    for names in children.values():
        names.sort()
    roots.sort()

    lines = [f"Armature: {arm.name}", f"Bone count: {len(bones)}", ""]

    def visit(name, prefix="", last=True):
        lines.append(prefix + ("`- " if last else "|- ") + name)
        next_prefix = prefix + ("   " if last else "|  ")
        values = children[name]
        for index, child in enumerate(values):
            visit(child, next_prefix, index == len(values) - 1)

    for index, name in enumerate(roots):
        visit(name, "", index == len(roots) - 1)

    (root / "rig_bones.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def redraw_view(window, area, region):
    """Force Blender to refresh text/overlay state before a capture."""
    area.tag_redraw()
    with bpy.context.temp_override(window=window, area=area, region=region):
        try:
            bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=2)
        except RuntimeError:
            # Xvfb can occasionally report no timer context. area.tag_redraw()
            # still marks the editor dirty for the following capture operator.
            pass


def render_viewport(path: Path, *, window, area, region):
    bpy.context.scene.render.filepath = str(path.resolve())
    redraw_view(window, area, region)
    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.render.opengl(write_still=True, view_context=True)


def screenshot_view3d(path: Path, *, window, area, region):
    """Capture the real 3D editor, including text overlays such as bone names."""
    redraw_view(window, area, region)
    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.screen.screenshot_area(
            filepath=str(path.resolve()),
            check_existing=False,
            hide_props_region=True,
        )


def render_default_rig(arm, root, window, area, region):
    scene = bpy.context.scene
    old_resolution = (
        scene.render.resolution_x,
        scene.render.resolution_y,
        scene.render.resolution_percentage,
    )
    old_pose_position = arm.data.pose_position
    old_frame = scene.frame_current

    scene.render.resolution_x = 768
    scene.render.resolution_y = 768
    scene.render.resolution_percentage = 100
    scene.frame_set(scene.frame_start)
    arm.data.pose_position = "REST"
    set_sword_visible(False)
    bpy.context.view_layer.update()

    arm.data.show_names = False
    render_viewport(
        root / "rig_default_overview.png",
        window=window, area=area, region=region,
    )

    # Current Blender Viewport Render omits bone-name text even when Names is
    # enabled. Capture Blender's real editor instead so labels remain genuine.
    arm.data.show_names = True
    screenshot_view3d(
        root / "rig_default_labeled.png",
        window=window, area=area, region=region,
    )

    arm.data.show_names = False
    arm.data.pose_position = old_pose_position
    set_sword_visible(True)
    scene.render.resolution_x = old_resolution[0]
    scene.render.resolution_y = old_resolution[1]
    scene.render.resolution_percentage = old_resolution[2]
    scene.frame_set(old_frame)
    bpy.context.view_layer.update()


def render_animation(arm, output, window, area, region):
    scene = bpy.context.scene
    arm.data.pose_position = "POSE"
    arm.data.show_names = False
    set_sword_visible(True)
    for frame in range(scene.frame_start, scene.frame_end + 1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        render_viewport(
            output / f"{frame:02d}.png",
            window=window, area=area, region=region,
        )


def main() -> int:
    args = parse_args()
    output = Path(args.output).resolve()
    root = Path(args.rig_output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    root.mkdir(parents=True, exist_ok=True)

    arm = find_armature()
    prepare_armature(arm)
    window, area, region, space = find_view3d_context()
    configure_view(space)

    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.view3d.view_camera()

    write_rig_manifest(arm, root)
    render_default_rig(arm, root, window, area, region)
    render_animation(arm, output, window, area, region)

    print(
        f"anim2sheet: actual Blender armature render OK -> {output}; "
        f"default rig docs -> {root}"
    )
    bpy.ops.wm.quit_blender()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
