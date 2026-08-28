"""Blender-native Gale Slash POC: build rig, procedural action, render and save source.blend."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def argv():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def add_bone(eb, name, head, tail, parent=None):
    bone = eb.new(name); bone.head = head; bone.tail = tail
    if parent: bone.parent = parent
    return bone


def material(name, color, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1.0)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.55
    bsdf.inputs["Metallic"].default_value = metallic
    return mat


def weighted_cylinder(armature, name, bone_name, head, tail, radius, mat):
    a, b = Vector(head), Vector(tail); d = b - a
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=radius, depth=d.length, location=(a + b) * 0.5)
    obj = bpy.context.object; obj.name = name
    obj.rotation_mode = "QUATERNION"; obj.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj.data.materials.append(mat)
    group = obj.vertex_groups.new(name=bone_name); group.add(range(len(obj.data.vertices)), 1.0, "REPLACE")
    mod = obj.modifiers.new("Armature", "ARMATURE"); mod.object = armature
    return obj


def weighted_sphere(armature, name, bone_name, center, radius, mat):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=radius, location=center)
    obj = bpy.context.object; obj.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj.data.materials.append(mat)
    group = obj.vertex_groups.new(name=bone_name); group.add(range(len(obj.data.vertices)), 1.0, "REPLACE")
    mod = obj.modifiers.new("Armature", "ARMATURE"); mod.object = armature
    return obj


def build_rig():
    arm_data = bpy.data.armatures.new("GameHumanoidV1")
    arm = bpy.data.objects.new("GameHumanoidV1", arm_data); bpy.context.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm; arm.select_set(True); bpy.ops.object.mode_set(mode="EDIT")
    eb = arm_data.edit_bones
    hips = add_bone(eb, "Hips", (0,0,1.00), (0,0,1.18))
    spine = add_bone(eb, "Spine", (0,0,1.18), (0,0,1.55), hips)
    neck = add_bone(eb, "Neck", (0,0,1.55), (0,0,1.70), spine)
    add_bone(eb, "Head", (0,0,1.70), (0,0,1.93), neck)
    ls = add_bone(eb, "LeftShoulder", (0,0,1.53), (-0.18,0,1.53), spine)
    lua = add_bone(eb, "LeftUpperArm", (-0.18,0,1.53), (-0.47,0,1.42), ls)
    lfa = add_bone(eb, "LeftForeArm", (-0.47,0,1.42), (-0.69,0,1.25), lua)
    add_bone(eb, "LeftHand", (-0.69,0,1.25), (-0.78,0,1.18), lfa)
    rs = add_bone(eb, "RightShoulder", (0,0,1.53), (0.18,0,1.53), spine)
    rua = add_bone(eb, "RightUpperArm", (0.18,0,1.53), (0.47,0,1.42), rs)
    rfa = add_bone(eb, "RightForeArm", (0.47,0,1.42), (0.69,0,1.25), rua)
    add_bone(eb, "RightHand", (0.69,0,1.25), (0.78,0,1.18), rfa)
    lt = add_bone(eb, "LeftUpLeg", (-0.11,0,1.00), (-0.13,0,0.58), hips)
    ll = add_bone(eb, "LeftLeg", (-0.13,0,0.58), (-0.13,0,0.15), lt)
    add_bone(eb, "LeftFoot", (-0.13,0,0.15), (-0.13,-0.18,0.08), ll)
    rt = add_bone(eb, "RightUpLeg", (0.11,0,1.00), (0.13,0,0.58), hips)
    rl = add_bone(eb, "RightLeg", (0.13,0,0.58), (0.13,0,0.15), rt)
    add_bone(eb, "RightFoot", (0.13,0,0.15), (0.13,-0.18,0.08), rl)
    bpy.ops.object.mode_set(mode="POSE")
    for bone in arm.pose.bones: bone.rotation_mode = "XYZ"
    bpy.ops.object.mode_set(mode="OBJECT")
    return arm


def build_character(arm):
    cloth = material("Cloth", (0.07,0.15,0.30)); skin = material("Skin", (0.72,0.48,0.32)); boots = material("Boots", (0.055,0.04,0.035)); steel = material("Steel", (0.55,0.62,0.70), 0.75)
    bones = arm.data.bones
    for name, radius, mat in [
        ("Spine",0.17,cloth),("LeftUpperArm",0.075,cloth),("LeftForeArm",0.065,skin),("RightUpperArm",0.075,cloth),("RightForeArm",0.065,skin),
        ("LeftUpLeg",0.10,cloth),("LeftLeg",0.085,boots),("RightUpLeg",0.10,cloth),("RightLeg",0.085,boots)]:
        b = bones[name]; weighted_cylinder(arm, f"Body_{name}", name, b.head_local, b.tail_local, radius, mat)
    weighted_sphere(arm, "HeadMesh", "Head", (0,0,1.82), 0.15, skin)
    weighted_sphere(arm, "PelvisMesh", "Hips", (0,0,1.07), 0.18, cloth)
    # Sword is rigidly weighted to RightHand and starts as a long diagonal extension from the grip.
    weighted_cylinder(arm, "Sword", "RightHand", (0.73,0,1.23), (1.58,0,1.72), 0.035, steel)
    return Vector((1.58,0,1.72))


def key(arm, frame, root_x, hips_y, spine_y, rua_y, rfa_y, lua_y, lfa_y, left_leg_y=0.0, right_leg_y=0.0):
    bpy.context.scene.frame_set(frame)
    arm.location.x = root_x; arm.keyframe_insert(data_path="location", frame=frame)
    values = {"Hips":hips_y,"Spine":spine_y,"RightUpperArm":rua_y,"RightForeArm":rfa_y,"LeftUpperArm":lua_y,"LeftForeArm":lfa_y,"LeftUpLeg":left_leg_y,"RightUpLeg":right_leg_y}
    for name, degrees in values.items():
        bone = arm.pose.bones[name]; bone.rotation_euler.y = math.radians(degrees); bone.keyframe_insert(data_path="rotation_euler", frame=frame)


def animate(arm, frames):
    scene = bpy.context.scene; scene.frame_start = 1; scene.frame_end = frames
    # Keep torso rotation restrained so the silhouette reads as an arm-driven
    # horizontal sword sweep instead of the whole character turning sideways.
    poses = [
        (1,0.00,0,0,-20,20,18,-20,0,0),
        (4,0.00,-5,-8,-95,20,-60,18,8,-4),
        (7,0.08,5,8,-30,10,5,-8,-10,8),
        (10,0.20,10,15,100,-10,60,-20,-15,12),
        (13,0.27,12,18,165,-5,95,-25,-8,6),
        (16,0.30,0,0,-15,20,18,-20,0,0),
    ]
    for pose in poses: key(arm, *pose)
    action = arm.animation_data.action; action.name = "GaleSlash"
    for curve in action.fcurves:
        for point in curve.keyframe_points: point.interpolation = "BEZIER"


def setup_scene(canvas):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"; scene.render.film_transparent = True
    scene.render.resolution_x = int(canvas[0]); scene.render.resolution_y = int(canvas[1]); scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"; scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"; scene.view_settings.look = "AgX - Medium High Contrast"
    if getattr(scene, "eevee", None) is not None:
        scene.eevee.taa_render_samples = 8
    bpy.ops.object.light_add(type="AREA", location=(0,-4,5)); light=bpy.context.object; light.data.energy=700; light.data.shape="DISK"; light.data.size=5
    bpy.ops.object.camera_add(location=(0,-7.5,2.35)); cam=bpy.context.object; cam.data.type="ORTHO"; cam.data.ortho_scale=3.55; cam.rotation_euler=(math.radians(78),0,0)
    # Point camera to chest.
    direction = Vector((0,0,1.12)) - cam.location; cam.rotation_euler = direction.to_track_quat("-Z","Y").to_euler(); scene.camera = cam
    scene.world.color = (0.035,0.035,0.035)


def sample_debug(arm, sword_tip_rest, frames):
    samples=[]; rest = arm.data.bones["RightHand"].matrix_local
    for frame in range(1, frames+1):
        bpy.context.scene.frame_set(frame)
        pose = arm.pose.bones["RightHand"].matrix
        tip = pose @ rest.inverted() @ sword_tip_rest
        samples.append({"frame":frame,"rootX":round(arm.location.x,6),"swordTip":[round(tip.x,6),round(tip.y,6),round(tip.z,6)]})
    return samples


def main():
    parser=argparse.ArgumentParser(add_help=False); parser.add_argument("--spec",required=True); parser.add_argument("--output",required=True); args,_=parser.parse_known_args(argv())
    source=json.loads(Path(args.spec).read_text(encoding="utf-8")); output=Path(args.output); frames=int(source["frames"])
    bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete(use_global=False)
    arm=build_rig(); sword_tip=build_character(arm); animate(arm,frames); setup_scene(source["canvas"])
    debug={"action":source["action"],"samples":sample_debug(arm,sword_tip,frames)}
    (output/"motion_debug.json").write_text(json.dumps(debug,indent=2)+"\n",encoding="utf-8")
    bpy.context.scene.frame_set(1); bpy.ops.wm.save_as_mainfile(filepath=str((output/"source.blend").resolve()))
    frame_dir=output/"frames"; frame_dir.mkdir(parents=True,exist_ok=True)
    for frame in range(1,frames+1):
        bpy.context.scene.frame_set(frame); bpy.context.scene.render.filepath=str((frame_dir/f"{frame:02d}.png").resolve()); bpy.ops.render.render(write_still=True)
    print(f"anim2sheet Blender render OK: {frames} frames")
    return 0


if __name__ == "__main__": raise SystemExit(main())
