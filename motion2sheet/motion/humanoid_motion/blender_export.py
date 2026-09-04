from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

import bpy
from mathutils import Quaternion, Vector

from motion2sheet.motion.humanoid_motion.blender_math import (
    continuous_quaternion_values,
    mean_leg_length,
    vector_values,
    world_pose_matrix,
    world_rest_matrix,
    yaw_twist,
)
from motion2sheet.motion.humanoid_motion.mapping import read_mapping, validate_character_mapping
from motion2sheet.motion.humanoid_motion.schema import (
    ANIMATION_SCHEMA,
    CANONICAL_SKELETON_ID,
    EXPECTED_COORDINATE_SYSTEM,
    EXPECTED_QUATERNION_CONVENTION,
    MAPPED_JOINTS,
    ROTATION_JOINTS,
    write_animation,
)
from motion2sheet.motion.roundtrip.blender_json_scene import build_json_scene
from motion2sheet.motion.roundtrip.schema import read_json, validate_animation_document, validate_rig_document


def _argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    args = parser.parse_args(_argv())
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    source_rig = validate_rig_document(read_json(Path(request["sourceRigPath"])))
    source_animation = validate_animation_document(read_json(Path(request["sourceAnimationPath"])), source_rig)
    mapping = validate_character_mapping(read_mapping(Path(request["mappingPath"])), source_rig)
    armature, _action = build_json_scene(source_rig, source_animation)
    joints = mapping["joints"]
    leg_length = mean_leg_length(armature, joints)
    frames = [int(row["frame"]) for row in source_animation["frames"]]
    hips_name = joints["Hips"]

    bpy.context.scene.frame_set(frames[0])
    bpy.context.view_layer.update()
    first_hips_pose = world_pose_matrix(armature, hips_name)
    first_hips_position = armature.matrix_world @ armature.pose.bones[hips_name].head
    first_hips_rotation = first_hips_pose.to_quaternion().normalized()
    rest_hips_position = armature.matrix_world @ armature.data.bones[hips_name].head_local
    rest_rotations = {
        semantic: world_rest_matrix(armature, bone_name).to_quaternion().normalized()
        for semantic, bone_name in joints.items()
    }
    bpy.context.scene.frame_set(frames[-1])
    bpy.context.view_layer.update()
    last_hips_position = armature.matrix_world @ armature.pose.bones[hips_name].head
    source_planar_displacement = (last_hips_position - first_hips_position) / leg_length
    source_planar_displacement.z = 0.0

    root_translations: list[list[float]] = []
    root_rotations: list[Quaternion] = []
    hips_translations: list[list[float]] = []
    rotations: dict[str, list[Quaternion]] = {semantic: [] for semantic in MAPPED_JOINTS}
    source_vertical_offsets: list[float] = []
    canonical_vertical_offsets: list[float] = []
    for sample, frame in enumerate(frames):
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        hips_pose = world_pose_matrix(armature, hips_name)
        hips_position = armature.matrix_world @ armature.pose.bones[hips_name].head
        hips_rotation = hips_pose.to_quaternion().normalized()
        root_rotation = yaw_twist(hips_rotation @ first_hips_rotation.inverted())
        progress = sample / (len(frames) - 1) if len(frames) > 1 else 0.0
        stripped_planar_travel = source_planar_displacement * progress
        root_translation = Vector((0.0, 0.0, 0.0))
        source_offset = (hips_position - rest_hips_position) / leg_length
        hips_translation = root_rotation.inverted() @ (
            source_offset - stripped_planar_travel
        )
        root_translations.append(vector_values(root_translation))
        root_rotations.append(root_rotation)
        hips_translations.append(vector_values(hips_translation))
        source_vertical_offsets.append(float(source_offset.z))
        canonical_vertical_offsets.append(float(hips_translation.z))
        for semantic, bone_name in joints.items():
            pose_rotation = world_pose_matrix(armature, bone_name).to_quaternion().normalized()
            delta = root_rotation.inverted() @ pose_rotation @ rest_rotations[semantic].inverted()
            rotations[semantic].append(delta.normalized())

    document = {
        "schema": ANIMATION_SCHEMA,
        "version": 1,
        "id": request["animationId"],
        "canonicalSkeleton": CANONICAL_SKELETON_ID,
        "fps": float(source_animation["fps"]),
        "frameCount": len(frames),
        "loop": bool(request["loop"]),
        "coordinateSystem": dict(EXPECTED_COORDINATE_SYSTEM),
        "quaternionConvention": dict(EXPECTED_QUATERNION_CONVENTION),
        "root": {
            "translations": root_translations,
            "rotations": continuous_quaternion_values(root_rotations),
        },
        "hips": {
            "translations": hips_translations,
            "rotations": continuous_quaternion_values(rotations["Hips"]),
        },
        "joints": {
            semantic: {"rotations": continuous_quaternion_values(rotations[semantic])}
            for semantic in ROTATION_JOINTS
        },
    }
    output = Path(request["animationOutput"])
    write_animation(output, document)
    report = {
        "schema": "motion2sheet.humanoid-motion.export-diagnostics",
        "version": 1,
        "animationId": document["id"],
        "canonicalSkeleton": CANONICAL_SKELETON_ID,
        "sourceContract": "Contract B",
        "sourceFbxRead": False,
        "sourceFrameRange": frames,
        "frameCount": len(frames),
        "fps": document["fps"],
        "sourceMeanLegLengthSceneUnits": leg_length,
        "rootPolicy": "virtual Root translation fixed at zero; relative Hips yaw retained only as canonical body orientation",
        "locomotionPolicy": "linear-endpoint-planar-detrend-v1",
        "sourcePlanarEndToEnd": vector_values(source_planar_displacement),
        "sourcePlanarDisplacement": float(source_planar_displacement.length),
        "strippedPlanarEndToEnd": vector_values(source_planar_displacement),
        "rootTranslationMaxAbsComponent": 0.0,
        "sourceHipsVerticalRange": max(source_vertical_offsets) - min(source_vertical_offsets),
        "canonicalHipsVerticalRange": max(canonical_vertical_offsets) - min(canonical_vertical_offsets),
        "translationPolicy": "dimensionless mean-leg-length units",
        "rotationFormula": "D = inverse(Qroot) * Rpose * inverse(Rrest)",
        "sourceBoneNamesStoredInAnimation": False,
    }
    report_path = Path(request["diagnosticsOutput"])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
