"""Render the actual Blender armature for animation and default-rig inspection.

Animated skeleton frames and both default-rig diagnostics use Blender Viewport
Render (``bpy.ops.render.opengl``). Blender does not reliably include bone-name
text overlays in Viewport Render, so the labeled diagnostic creates temporary
Blender FONT objects from the armature's real bone names and places them beside
the corresponding rest bones before rendering.

No bones or labels are re-drawn with Pillow, ImageDraw, proxy meshes, or an
external renderer. The temporary FONT objects are never saved to source.blend.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


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


def render_viewport(path: Path, *, window, area, region):
    bpy.context.scene.render.filepath = str(path.resolve())
    area.tag_redraw()
    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.render.opengl(write_still=True, view_context=True)


def create_bone_labels(arm):
    """Create temporary Blender text objects beside every rest bone.

    Labels are generated directly from ``arm.data.bones`` so the diagnostic can
    never drift from the actual rig naming. The camera views the character from
    negative Y, therefore a +90 degree X rotation makes text face the camera
    while keeping its local Y axis upright in world Z.
    """
    material = bpy.data.materials.new("_Anim2SheetRigLabelMaterial")
    material.diffuse_color = (0.95, 0.95, 0.95, 1.0)

    labels = []
    for bone in arm.data.bones:
        curve = bpy.data.curves.new(f"_RigLabelCurve_{bone.name}", type="FONT")
        curve.body = bone.name
        curve.size = 0.055
        curve.space_character = 1.0
        curve.align_y = "CENTER"
        curve.materials.append(material)

        obj = bpy.data.objects.new(f"_RigLabel_{bone.name}", curve)
        bpy.context.collection.objects.link(obj)
        obj.rotation_euler = (math.radians(90.0), 0.0, 0.0)
        obj.show_in_front = True

        midpoint_local = (Vector(bone.head_local) + Vector(bone.tail_local)) * 0.5
        midpoint_world = arm.matrix_world @ midpoint_local

        if bone.name.startswith("Left"):
            curve.align_x = "RIGHT"
            offset_x = -0.075
        elif bone.name.startswith("Right"):
            curve.align_x = "LEFT"
            offset_x = 0.075
        else:
            curve.align_x = "LEFT"
            offset_x = 0.075

        # Pull text slightly toward the camera so it stays readable over bones.
        obj.location = midpoint_world + Vector((offset_x, -0.08, 0.0))
        labels.append(obj)

    return labels, material


def hide_and_remove_labels(labels, material):
    for obj in labels:
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data.users == 0:
            bpy.data.curves.remove(data)
    if material.users == 0:
        bpy.data.materials.remove(material)


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

    render_viewport(
        root / "rig_default_overview.png",
        window=window,
        area=area,
        region=region,
    )

    labels, label_material = create_bone_labels(arm)
    bpy.context.view_layer.update()
    render_viewport(
        root / "rig_default_labeled.png",
        window=window,
        area=area,
        region=region,
    )
    hide_and_remove_labels(labels, label_material)

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
            window=window,
            area=area,
            region=region,
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
