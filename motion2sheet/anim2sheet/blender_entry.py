"""Blender-native reference-driven Gale Slash POC.

The generated sprite sheet reference is authoritative for pose/timing/weapon trajectory only.
Blender owns rig solving, interpolation, rendering, and the authoritative source.blend.
"""
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
    bone = eb.new(name)
    bone.head = head
    bone.tail = tail
    if parent:
        bone.parent = parent
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


def weighted_cylinder(arm, name, bone_name, head, tail, radius, mat, vertices=12):
    a, b = Vector(head), Vector(tail)
    direction = b - a
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=direction.length, location=(a + b) * 0.5)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(direction.normalized())
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj.data.materials.append(mat)
    group = obj.vertex_groups.new(name=bone_name)
    group.add(range(len(obj.data.vertices)), 1.0, "REPLACE")
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    return obj


def weighted_sphere(arm, name, bone_name, center, radius, mat):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=radius, location=center)
    obj = bpy.context.object
    obj.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj.data.materials.append(mat)
    group = obj.vertex_groups.new(name=bone_name)
    group.add(range(len(obj.data.vertices)), 1.0, "REPLACE")
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    return obj


def controller_cylinder(parent, name, z0, z1, radius, mat):
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=radius, depth=z1 - z0, location=(0, 0, (z0 + z1) * 0.5))
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    obj.parent = parent
    return obj


def build_root_and_rig():
    root = bpy.data.objects.new("MotionRoot", None)
    bpy.context.collection.objects.link(root)
    data = bpy.data.armatures.new("GameHumanoidV1")
    arm = bpy.data.objects.new("GameHumanoidV1", data)
    bpy.context.collection.objects.link(arm)
    arm.parent = root
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = data.edit_bones
    hips = add_bone(eb, "Hips", (0, 0, 0.98), (0, 0, 1.18))
    spine = add_bone(eb, "Spine", (0, 0, 1.18), (0, 0, 1.55), hips)
    neck = add_bone(eb, "Neck", (0, 0, 1.55), (0, 0, 1.70), spine)
    add_bone(eb, "Head", (0, 0, 1.70), (0, 0, 1.93), neck)
    ls = add_bone(eb, "LeftShoulder", (0, 0, 1.53), (-0.18, 0, 1.53), spine)
    lua = add_bone(eb, "LeftUpperArm", (-0.18, 0, 1.53), (-0.46, 0, 1.42), ls)
    lfa = add_bone(eb, "LeftForeArm", (-0.46, 0, 1.42), (-0.68, 0, 1.25), lua)
    add_bone(eb, "LeftHand", (-0.68, 0, 1.25), (-0.77, 0, 1.18), lfa)
    rs = add_bone(eb, "RightShoulder", (0, 0, 1.53), (0.18, 0, 1.53), spine)
    rua = add_bone(eb, "RightUpperArm", (0.18, 0, 1.53), (0.46, 0, 1.42), rs)
    rfa = add_bone(eb, "RightForeArm", (0.46, 0, 1.42), (0.68, 0, 1.25), rua)
    add_bone(eb, "RightHand", (0.68, 0, 1.25), (0.77, 0, 1.18), rfa)
    lt = add_bone(eb, "LeftUpLeg", (-0.18, 0, 0.98), (-0.24, 0, 0.56), hips)
    ll = add_bone(eb, "LeftLeg", (-0.24, 0, 0.56), (-0.30, 0, 0.15), lt)
    add_bone(eb, "LeftFoot", (-0.30, 0, 0.15), (-0.30, -0.22, 0.08), ll)
    rt = add_bone(eb, "RightUpLeg", (0.18, 0, 0.98), (0.24, 0, 0.56), hips)
    rl = add_bone(eb, "RightLeg", (0.24, 0, 0.56), (0.30, 0, 0.15), rt)
    add_bone(eb, "RightFoot", (0.30, 0, 0.15), (0.30, -0.22, 0.08), rl)
    bpy.ops.object.mode_set(mode="POSE")
    for bone in arm.pose.bones:
        bone.rotation_mode = "XYZ"
    bpy.ops.object.mode_set(mode="OBJECT")
    return root, arm


def build_character(arm):
    cloth = material("Cloth", (0.07, 0.15, 0.30))
    skin = material("Skin", (0.72, 0.48, 0.32))
    boots = material("Boots", (0.055, 0.04, 0.035))
    bones = arm.data.bones
    for name, radius, mat in [("Spine",0.18,cloth),("LeftUpperArm",0.08,cloth),("LeftForeArm",0.07,skin),("RightUpperArm",0.08,cloth),("RightForeArm",0.07,skin),("LeftUpLeg",0.11,cloth),("LeftLeg",0.09,boots),("RightUpLeg",0.11,cloth),("RightLeg",0.09,boots)]:
        b = bones[name]
        weighted_cylinder(arm, "Body_" + name, name, b.head_local, b.tail_local, radius, mat)
    weighted_sphere(arm, "HeadMesh", "Head", (0,0,1.82), 0.15, skin)
    weighted_sphere(arm, "PelvisMesh", "Hips", (0,0,1.07), 0.20, cloth)
    for name, center, radius, mat in [("LeftUpperArm",(-0.18,0,1.53),0.085,skin),("RightUpperArm",(0.18,0,1.53),0.085,skin),("LeftForeArm",(-0.46,0,1.42),0.075,skin),("RightForeArm",(0.46,0,1.42),0.075,skin),("LeftHand",(-0.725,0,1.215),0.075,skin),("RightHand",(0.725,0,1.215),0.075,skin),("LeftLeg",(-0.24,0,0.56),0.095,cloth),("RightLeg",(0.24,0,0.56),0.095,cloth)]:
        weighted_sphere(arm, "Joint_" + name, name, center, radius, mat)


def empty(name, parent=None, location=(0,0,0)):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    if parent:
        obj.parent = parent
    return obj


def build_pose_targets(root, arm):
    targets = {
        "leftWrist": empty("LeftWristTarget", root),
        "rightWrist": empty("RightWristTarget", root),
        "leftAnkle": empty("LeftAnkleTarget"),
        "rightAnkle": empty("RightAnkleTarget"),
    }
    left_elbow_pole = empty("LeftElbowPole", root, (-0.55,-0.90,1.30))
    right_elbow_pole = empty("RightElbowPole", root, (0.55,-0.90,1.30))
    left_knee_pole = empty("LeftKneePole", None, (-0.25,-0.90,0.55))
    right_knee_pole = empty("RightKneePole", None, (0.25,-0.90,0.55))
    for bone_name, target_name, pole in [("LeftForeArm","leftWrist",left_elbow_pole),("RightForeArm","rightWrist",right_elbow_pole),("LeftLeg","leftAnkle",left_knee_pole),("RightLeg","rightAnkle",right_knee_pole)]:
        ik = arm.pose.bones[bone_name].constraints.new("IK")
        ik.name = "ReferenceIK_" + bone_name
        ik.target = targets[target_name]
        ik.pole_target = pole
        ik.chain_count = 2
        ik.iterations = 64
    return targets


def build_sword(root):
    steel = material("Steel", (0.55,0.62,0.70),0.75)
    grip_mat = material("Grip", (0.12,0.055,0.025),0.10)
    ctrl = empty("SwordController", root)
    ctrl.rotation_mode = "QUATERNION"
    controller_cylinder(ctrl,"SwordGrip",-0.08,0.24,0.045,grip_mat)
    controller_cylinder(ctrl,"SwordBlade",0.23,1.20,0.035,steel)
    return ctrl


def key_pose(root, arm, targets, sword, row):
    frame = int(row["frame"])
    bpy.context.scene.frame_set(frame)
    root_x, root_z = row["root"]
    root.location = (root_x, 0.0, root_z)
    root.keyframe_insert(data_path="location", frame=frame)
    body = row["body"]
    for name, key in [("Hips","hipsLeanDeg"),("Spine","spineLeanDeg"),("Head","headLeanDeg")]:
        bone = arm.pose.bones[name]
        bone.rotation_euler.y = math.radians(float(body[key]))
        bone.keyframe_insert(data_path="rotation_euler", frame=frame)
    row_targets = row["targets"]
    for name in ("leftAnkle","rightAnkle"):
        targets[name].location = Vector(row_targets[name])
        targets[name].keyframe_insert(data_path="location", frame=frame)
    grip = Vector(row_targets["swordGrip"])
    tip_guide = Vector(row_targets["swordTipGuide"])
    direction = tip_guide - grip
    if direction.length < 1e-6:
        raise RuntimeError(f"frame {frame}: sword grip/tip guide are coincident")
    axis = direction.normalized()
    targets["rightWrist"].location = grip - axis * 0.025
    targets["leftWrist"].location = grip + axis * 0.145
    targets["rightWrist"].keyframe_insert(data_path="location", frame=frame)
    targets["leftWrist"].keyframe_insert(data_path="location", frame=frame)
    sword.location = grip
    sword.rotation_quaternion = Vector((0,0,1)).rotation_difference(axis)
    sword.keyframe_insert(data_path="location", frame=frame)
    sword.keyframe_insert(data_path="rotation_quaternion", frame=frame)


def configure_interpolation(owner, strike_frames):
    action = owner.animation_data.action if owner.animation_data else None
    if not action:
        return
    for curve in action.fcurves:
        for point in curve.keyframe_points:
            frame = int(round(point.co.x))
            point.interpolation = "LINEAR" if frame in strike_frames else "BEZIER"
            point.handle_left_type = "AUTO_CLAMPED"
            point.handle_right_type = "AUTO_CLAMPED"


def animate_from_reference(root, arm, targets, sword, reference, frames):
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = frames
    poses = reference["keyPoses"]
    if len(poses) != frames:
        raise RuntimeError(f"reference key pose count {len(poses)} != frames {frames}")
    for row in poses:
        key_pose(root, arm, targets, sword, row)
    strike_frames = set(int(v) for v in reference.get("solver", {}).get("strikeFrames", []))
    for owner in [root, arm, sword, *targets.values()]:
        configure_interpolation(owner, strike_frames)
    if root.animation_data and root.animation_data.action:
        root.animation_data.action.name = "GaleSlashRoot"
    if arm.animation_data and arm.animation_data.action:
        arm.animation_data.action.name = "GaleSlashBody"
    if sword.animation_data and sword.animation_data.action:
        sword.animation_data.action.name = "GaleSlashSword"


def setup_scene(canvas):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.film_transparent = True
    scene.render.resolution_x = int(canvas[0]); scene.render.resolution_y = int(canvas[1]); scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"; scene.render.image_settings.color_mode = "RGBA"; scene.render.image_settings.color_depth = "8"
    scene.view_settings.look = "AgX - Medium High Contrast"
    if getattr(scene,"eevee",None) is not None:
        scene.eevee.taa_render_samples = 8
    bpy.ops.object.light_add(type="AREA", location=(0,-4,5))
    light = bpy.context.object; light.data.energy = 700; light.data.size = 5
    bpy.ops.object.camera_add(location=(0.15,-7.5,2.25))
    cam = bpy.context.object; cam.data.type = "ORTHO"; cam.data.ortho_scale = 3.55
    direction = Vector((0.15,0,1.08)) - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z","Y").to_euler(); scene.camera = cam
    scene.world.color = (0.035,0.035,0.035)


def world_point(obj, local):
    return obj.matrix_world @ Vector(local)


def bone_tail_world(arm, name):
    return arm.matrix_world @ arm.pose.bones[name].tail


def sample_debug(root, arm, targets, sword, reference, frames):
    ref_by_frame = {int(row["frame"]): row for row in reference["keyPoses"]}
    samples=[]
    for frame in range(1, frames+1):
        bpy.context.scene.frame_set(frame); bpy.context.view_layer.update()
        sword_grip = world_point(sword,(0,0,0)); sword_tip = world_point(sword,(0,0,1.20))
        actual = {"leftWrist":bone_tail_world(arm,"LeftForeArm"),"rightWrist":bone_tail_world(arm,"RightForeArm"),"leftAnkle":bone_tail_world(arm,"LeftLeg"),"rightAnkle":bone_tail_world(arm,"RightLeg")}
        target_world = {name:targets[name].matrix_world.translation.copy() for name in ("leftWrist","rightWrist","leftAnkle","rightAnkle")}
        errors = {name:(actual[name]-target_world[name]).length for name in actual}
        ref = ref_by_frame[frame]
        samples.append({"frame":frame,"phase":ref["phase"],"root":[round(root.location.x,6),round(root.location.z,6)],"swordGrip":[round(v,6) for v in sword_grip],"swordTip":[round(v,6) for v in sword_tip],"projectedSwordLengthXZ":round(math.hypot(sword_tip.x-sword_grip.x,sword_tip.z-sword_grip.z),6),"ikError":{name:round(value,6) for name,value in errors.items()}})
    return samples


def main():
    parser=argparse.ArgumentParser(add_help=False); parser.add_argument("--spec",required=True); parser.add_argument("--output",required=True); args,_=parser.parse_known_args(argv())
    source=json.loads(Path(args.spec).read_text(encoding="utf-8")); output=Path(args.output); frames=int(source["frames"])
    reference=source.get("poseReferenceData")
    if not isinstance(reference,dict):
        raise RuntimeError("source spec missing embedded poseReferenceData")
    bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete(use_global=False)
    root,arm=build_root_and_rig(); build_character(arm); targets=build_pose_targets(root,arm); sword=build_sword(root); animate_from_reference(root,arm,targets,sword,reference,frames); setup_scene(source["canvas"])
    debug={"action":source["action"],"reference":reference.get("name"),"impactFrame":reference.get("solver",{}).get("impactFrame"),"samples":sample_debug(root,arm,targets,sword,reference,frames)}
    (output/"motion_debug.json").write_text(json.dumps(debug,indent=2)+"\n",encoding="utf-8")
    bpy.context.scene.frame_set(1); bpy.ops.wm.save_as_mainfile(filepath=str((output/"source.blend").resolve()))
    frame_dir=output/"frames"; frame_dir.mkdir(parents=True,exist_ok=True)
    for frame in range(1,frames+1):
        bpy.context.scene.frame_set(frame); bpy.context.scene.render.filepath=str((frame_dir/f"{frame:02d}.png").resolve()); bpy.ops.render.render(write_still=True)
    print(f"anim2sheet reference-driven Blender render OK: {frames} frames"); return 0


if __name__ == "__main__":
    raise SystemExit(main())
