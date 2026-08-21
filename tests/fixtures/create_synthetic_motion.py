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

    # Four key poses plus the loop-closing endpoint. Sampling 8 frames from this
    # range therefore includes true in-between poses rather than only three
    # repeated sine extrema.
    keys = [1, 5, 9, 13, 17]
    phases = [0.0, math.pi / 2.0, math.pi, 3.0 * math.pi / 2.0, 2.0 * math.pi]
    for frame, phase in zip(keys, phases):
        scene.frame_set(frame)
        swing = 0.55 * math.sin(phase)
        for name, angle in (
            ("LeftUpLeg", swing),
            ("RightUpLeg", -swing),
            ("LeftUpperArm", -0.75 * swing),
            ("RightUpperArm", 0.75 * swing),
        ):
            bone = armature.pose.bones[name]
            bone.rotation_euler.x = angle
            bone.keyframe_insert(data_path="rotation_euler", frame=frame)

        left_knee = armature.pose.bones["LeftLeg"]
        right_knee = armature.pose.bones["RightLeg"]
        left_knee.rotation_euler.x = max(0.0, -swing) * 0.65
        right_knee.rotation_euler.x = max(0.0, swing) * 0.65
        left_knee.keyframe_insert(data_path="rotation_euler", frame=frame)
        right_knee.keyframe_insert(data_path="rotation_euler", frame=frame)

    # Body bob is keyed at twice the step frequency.
    for frame, z in ((1, 0.00), (3, 0.04), (5, 0.00), (7, 0.04), (9, 0.00), (11, 0.04), (13, 0.00), (15, 0.04), (17, 0.00)):
        scene.frame_set(frame)
        armature.location.z = z
        armature.keyframe_insert(data_path="location", frame=frame)

    action = armature.animation_data.action
    if action is None:
        raise RuntimeError("Synthetic fixture failed to create an action")
    action.name = "SyntheticWalk"
    for fcurve in action.fcurves:
        for key in fcurve.keyframe_points:
            key.interpolation = "LINEAR"
    return action


def export_files(armature, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)

    # Export BVH first, then FBX. Explicit animation flags make the FBX fixture a
    # real round-trip test instead of accidentally accepting a rest-pose-only file.
    bpy.ops.export_anim.bvh(
        filepath=str(output / "synthetic_walk.bvh"),
        frame_start=1,
        frame_end=17,
        root_transform_only=False,
    )
    bpy.ops.export_scene.fbx(
        filepath=str(output / "synthetic_walk.fbx"),
        use_selection=True,
        object_types={"ARMATURE"},
        add_leaf_bones=False,
        bake_anim=True,
        bake_anim_use_nla_strips=False,
        bake_anim_use_all_actions=True,
        bake_anim_force_startend_keying=True,
        bake_anim_step=1.0,
        bake_anim_simplify_factor=0.0,
    )


def main():
    parsed = args()
    armature = build_armature()
    animate(armature)
    export_files(armature, Path(parsed.output).resolve())
    print(f"Synthetic motion fixtures written to {parsed.output}")


if __name__ == "__main__":
    main()
