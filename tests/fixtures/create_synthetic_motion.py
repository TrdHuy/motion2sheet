"""Create deterministic humanoid FBX and BVH motion fixtures for CI."""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import bpy


def argv():
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    return parser.parse_args(argv())


def add_bone(edit_bones, name, head, tail, parent=None):
    bone = edit_bones.new(name)
    bone.head = head
    bone.tail = tail
    if parent:
        bone.parent = parent
    return bone


def build_armature():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    armature_data = bpy.data.armatures.new("SyntheticHumanoid")
    armature = bpy.data.objects.new("SyntheticHumanoid", armature_data)
    bpy.context.collection.objects.link(armature)
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = armature_data.edit_bones

    pelvis = add_bone(eb, "Hips", (0, 0, 1.00), (0, 0, 1.20))
    spine = add_bone(eb, "Spine", (0, 0, 1.20), (0, 0, 1.55), pelvis)
    neck = add_bone(eb, "Neck", (0, 0, 1.55), (0, 0, 1.72), spine)
    add_bone(eb, "Head", (0, 0, 1.72), (0, 0, 1.95), neck)

    lsho = add_bone(eb, "LeftShoulder", (0, 0, 1.56), (-0.20, 0, 1.56), spine)
    lua = add_bone(eb, "LeftUpperArm", (-0.20, 0, 1.56), (-0.48, 0, 1.43), lsho)
    lfa = add_bone(eb, "LeftForeArm", (-0.48, 0, 1.43), (-0.68, 0, 1.22), lua)
    add_bone(eb, "LeftHand", (-0.68, 0, 1.22), (-0.75, 0, 1.12), lfa)

    rsho = add_bone(eb, "RightShoulder", (0, 0, 1.56), (0.20, 0, 1.56), spine)
    rua = add_bone(eb, "RightUpperArm", (0.20, 0, 1.56), (0.48, 0, 1.43), rsho)
    rfa = add_bone(eb, "RightForeArm", (0.48, 0, 1.43), (0.68, 0, 1.22), rua)
    add_bone(eb, "RightHand", (0.68, 0, 1.22), (0.75, 0, 1.12), rfa)

    lthigh = add_bone(eb, "LeftUpLeg", (-0.12, 0, 1.00), (-0.12, 0, 0.58), pelvis)
    lshin = add_bone(eb, "LeftLeg", (-0.12, 0, 0.58), (-0.12, 0, 0.16), lthigh)
    add_bone(eb, "LeftFoot", (-0.12, 0, 0.16), (-0.12, -0.18, 0.07), lshin)

    rthigh = add_bone(eb, "RightUpLeg", (0.12, 0, 1.00), (0.12, 0, 0.58), pelvis)
    rshin = add_bone(eb, "RightLeg", (0.12, 0, 0.58), (0.12, 0, 0.16), rthigh)
    add_bone(eb, "RightFoot", (0.12, 0, 0.16), (0.12, -0.18, 0.07), rshin)

    bpy.ops.object.mode_set(mode="POSE")
    for bone in armature.pose.bones:
        bone.rotation_mode = "XYZ"
    bpy.ops.object.mode_set(mode="OBJECT")
    return armature


def animate(armature):
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 17
    keys = [1, 3, 5, 7, 9, 11, 13, 15, 17]
    phases = [0, math.pi/2, math.pi, 3*math.pi/2, 2*math.pi, 5*math.pi/2, 3*math.pi, 7*math.pi/2, 4*math.pi]
    for frame, phase in zip(keys, phases):
        scene.frame_set(frame)
        armature.location.z = 0.025 * (1.0 - math.cos(phase * 2.0))
        armature.keyframe_insert(data_path="location", frame=frame)
        swing = 0.45 * math.sin(phase)
        for name, angle in (("LeftUpLeg", swing), ("RightUpLeg", -swing), ("LeftUpperArm", -0.7 * swing), ("RightUpperArm", 0.7 * swing)):
            bone = armature.pose.bones[name]
            bone.rotation_euler.x = angle
            bone.keyframe_insert(data_path="rotation_euler", frame=frame)
        armature.pose.bones["LeftLeg"].rotation_euler.x = max(0.0, -swing) * 0.55
        armature.pose.bones["RightLeg"].rotation_euler.x = max(0.0, swing) * 0.55
        armature.pose.bones["LeftLeg"].keyframe_insert(data_path="rotation_euler", frame=frame)
        armature.pose.bones["RightLeg"].keyframe_insert(data_path="rotation_euler", frame=frame)

    if armature.animation_data and armature.animation_data.action:
        for fcurve in armature.animation_data.action.fcurves:
            for key in fcurve.keyframe_points:
                key.interpolation = "LINEAR"


def export_files(armature, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.export_scene.fbx(
        filepath=str(output / "synthetic_walk.fbx"),
        use_selection=True,
        object_types={"ARMATURE"},
        add_leaf_bones=False,
        bake_anim=True,
        bake_anim_use_all_actions=False,
        bake_anim_simplify_factor=0.0,
    )
    bpy.ops.export_anim.bvh(
        filepath=str(output / "synthetic_walk.bvh"),
        frame_start=1,
        frame_end=17,
        root_transform_only=False,
    )


def main():
    parsed = args()
    armature = build_armature()
    animate(armature)
    export_files(armature, Path(parsed.output).resolve())
    print(f"Synthetic motion fixtures written to {parsed.output}")


if __name__ == "__main__":
    main()
