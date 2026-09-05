from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

import bpy
from mathutils import Matrix, Quaternion, Vector

from motion2sheet.motion.humanoid_motion.blender_math import (
    mean_leg_length,
    quaternion_values,
    rotation_error_degrees,
    vector_values,
    world_pose_matrix,
    world_rest_matrix,
)
from motion2sheet.motion.humanoid_motion.mapping import mapping_diagnostics, read_mapping, validate_character_mapping
from motion2sheet.motion.humanoid_motion.root_motion import humanoid_root_motion
from motion2sheet.motion.humanoid_motion.schema import CANONICAL_SKELETON, MAPPED_JOINTS, read_animation
from motion2sheet.motion.model_render.blender_helpers import (
    import_geometry_glb,
    mesh_layout,
    reconstruct_skin,
    setup_camera_and_render,
)
from motion2sheet.motion.roundtrip.blender_common import ordered_bones
from motion2sheet.motion.roundtrip.blender_json_scene import build_armature
from motion2sheet.motion.roundtrip.schema import read_json, validate_rig_document
from motion2sheet.motion.skin import compare_skin_bindings, validate_skin_document, verify_model_identity


def _argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _track_rotation(animation: dict, semantic: str, sample: int) -> Quaternion:
    values = animation["hips"]["rotations"][sample] if semantic == "Hips" else animation["joints"][semantic]["rotations"][sample]
    return Quaternion(values).normalized()


def _bridge_helpers(armature, joints: dict[str, str]) -> dict[str, tuple[str, str, float]]:
    result: dict[str, tuple[str, str, float]] = {}
    for child_semantic in MAPPED_JOINTS:
        parent_semantic = CANONICAL_SKELETON[child_semantic]
        if parent_semantic == "Root":
            continue
        child = armature.data.bones[joints[child_semantic]]
        parent_name = joints[parent_semantic]
        helpers = []
        current = child.parent
        while current is not None and current.name != parent_name:
            helpers.append(current.name)
            current = current.parent
        helpers.reverse()
        for index, name in enumerate(helpers, start=1):
            result[name] = (parent_semantic, child_semantic, index / (len(helpers) + 1))
    return result


def _build_runtime_action(armature, animation: dict, mapping: dict) -> tuple[object, dict]:
    scene = bpy.context.scene
    scene.render.fps = max(1, int(round(float(animation["fps"]))))
    scene.render.fps_base = scene.render.fps / float(animation["fps"])
    scene.frame_start = 1
    scene.frame_end = int(animation["frameCount"])
    action = bpy.data.actions.new(f"{animation['id']}__M2S_HUMANOID_MOTION_RUNTIME")
    armature.animation_data_create().action = action
    for pose_bone in armature.pose.bones:
        pose_bone.rotation_mode = "QUATERNION"

    joints = mapping["joints"]
    bone_to_semantic = {bone: semantic for semantic, bone in joints.items()}
    bridges = _bridge_helpers(armature, joints)
    order = ordered_bones(armature)
    leg_length = mean_leg_length(armature, joints)
    rest_world = {semantic: world_rest_matrix(armature, bone) for semantic, bone in joints.items()}
    rest_world_rotation = {semantic: matrix.to_quaternion().normalized() for semantic, matrix in rest_world.items()}
    rest_world_scale = {semantic: matrix.decompose()[2] for semantic, matrix in rest_world.items()}
    hips_rest_position = armature.matrix_world @ armature.data.bones[joints["Hips"]].head_local
    armature_inverse = armature.matrix_world.inverted_safe()

    for sample in range(animation["frameCount"]):
        frame = sample + 1
        scene.frame_set(frame)
        for pose_bone in armature.pose.bones:
            pose_bone.matrix_basis = Matrix.Identity(4)
        bpy.context.view_layer.update()

        root_rotation = Quaternion(animation["root"]["rotations"][sample]).normalized()
        root_translation = Vector(animation["root"]["translations"][sample]) * leg_length
        hips_track = animation["hips"]["translations"]
        hips_offset = Vector(hips_track[sample]) * leg_length if hips_track else Vector((0.0, 0.0, 0.0))
        semantic_world_rotation = {
            semantic: (root_rotation @ _track_rotation(animation, semantic, sample) @ rest_world_rotation[semantic]).normalized()
            for semantic in MAPPED_JOINTS
        }

        for data_bone in order:
            name = data_bone.name
            semantic = bone_to_semantic.get(name)
            bridge = bridges.get(name)
            if semantic is None and bridge is None:
                continue
            pose_bone = armature.pose.bones[name]
            if semantic is not None:
                desired_rotation = semantic_world_rotation[semantic]
                desired_scale = rest_world_scale[semantic]
            else:
                parent_semantic, child_semantic, factor = bridge
                desired_rotation = semantic_world_rotation[parent_semantic].slerp(semantic_world_rotation[child_semantic], factor).normalized()
                desired_scale = world_rest_matrix(armature, name).decompose()[2]

            if semantic == "Hips":
                desired_head = hips_rest_position + root_translation + root_rotation @ hips_offset
            elif pose_bone.parent is None:
                desired_head = armature.matrix_world @ data_bone.head_local
            else:
                parent_rest = data_bone.parent.matrix_local
                local_rest = parent_rest.inverted_safe() @ data_bone.matrix_local
                desired_parent_world = armature.matrix_world @ pose_bone.parent.matrix
                desired_head = desired_parent_world @ local_rest.translation
            desired_world = Matrix.LocRotScale(desired_head, desired_rotation, desired_scale)
            pose_bone.matrix = armature_inverse @ desired_world
            bpy.context.view_layer.update()

        for pose_bone in armature.pose.bones:
            location, rotation, scale = pose_bone.matrix_basis.decompose()
            pose_bone.location = location
            pose_bone.rotation_quaternion = rotation.normalized()
            pose_bone.scale = scale
            pose_bone.keyframe_insert(data_path="location", frame=frame, group=pose_bone.name)
            pose_bone.keyframe_insert(data_path="rotation_quaternion", frame=frame, group=pose_bone.name)
            pose_bone.keyframe_insert(data_path="scale", frame=frame, group=pose_bone.name)

    for fcurve in action.fcurves:
        for keyframe in fcurve.keyframe_points:
            keyframe.interpolation = "LINEAR"
    scene.frame_set(1)
    bpy.context.view_layer.update()
    return action, {
        "targetMeanLegLengthSceneUnits": leg_length,
        "bridgeHelpers": {name: {"from": value[0], "to": value[1], "factor": value[2]} for name, value in sorted(bridges.items())},
        "restWorldRotation": {semantic: quaternion_values(value) for semantic, value in rest_world_rotation.items()},
    }


def _playback_diagnostics(armature, animation: dict, mapping: dict, rig: dict, runtime: dict) -> tuple[dict, dict]:
    joints = mapping["joints"]
    leg_length = float(runtime["targetMeanLegLengthSceneUnits"])
    hips_name = joints["Hips"]
    hips_rest = armature.matrix_world @ armature.data.bones[hips_name].head_local
    rest_rotations = {semantic: world_rest_matrix(armature, bone).to_quaternion().normalized() for semantic, bone in joints.items()}
    max_rotation_error = 0.0
    worst_rotation = None
    max_hips_error = 0.0
    worst_hips = None
    finite = True
    for sample in range(animation["frameCount"]):
        bpy.context.scene.frame_set(sample + 1)
        bpy.context.view_layer.update()
        root_rotation = Quaternion(animation["root"]["rotations"][sample]).normalized()
        root_translation = Vector(animation["root"]["translations"][sample]) * leg_length
        hips_track = animation["hips"]["translations"]
        hips_offset = Vector(hips_track[sample]) * leg_length if hips_track else Vector((0.0, 0.0, 0.0))
        expected_hips = hips_rest + root_translation + root_rotation @ hips_offset
        actual_hips = armature.matrix_world @ armature.pose.bones[hips_name].head
        hips_error = (actual_hips - expected_hips).length
        if hips_error > max_hips_error:
            max_hips_error = hips_error
            worst_hips = {"sample": sample, "targetBone": hips_name}
        for semantic, bone_name in joints.items():
            pose_rotation = world_pose_matrix(armature, bone_name).to_quaternion().normalized()
            actual_delta = root_rotation.inverted() @ pose_rotation @ rest_rotations[semantic].inverted()
            expected_delta = _track_rotation(animation, semantic, sample)
            error = rotation_error_degrees(actual_delta, expected_delta)
            if error > max_rotation_error:
                max_rotation_error = error
                worst_rotation = {"sample": sample, "canonicalSemantic": semantic, "targetBone": bone_name}
            finite = finite and all(math.isfinite(value) for value in (*actual_delta, *actual_hips))

    root = humanoid_root_motion(animation)
    root_scene = {
        "unit": "scene-units",
        "start": [value * leg_length for value in root["start"]],
        "end": [value * leg_length for value in root["end"]],
        "delta": [value * leg_length for value in root["delta"]],
        "displacement": root["displacement"] * leg_length,
        "maxMagnitude": root["maxMagnitude"] * leg_length,
        "maxAbsComponent": root["maxAbsComponent"] * leg_length,
        "worstFrame": root["worstFrame"],
        "direction": root["direction"],
        "isInPlace": root["isInPlace"],
    }
    playback = {
        "schema": "motion2sheet.humanoid-motion.diagnostics.playback",
        "version": 1,
        "pass": finite and max_rotation_error <= 0.001 and max_hips_error <= 1e-5,
        "frameCount": animation["frameCount"],
        "mappedJointCount": len(joints),
        "leftRightIdentity": mapping_diagnostics(mapping, rig)["leftRightIdentity"],
        "quaternionValidity": True,
        "nanInfCheck": finite,
        "fullMappedJointPlayback": True,
        "maxSemanticRotationErrorDegrees": max_rotation_error,
        "worstSemanticRotation": worst_rotation,
        "maxHipsPositionError": max_hips_error,
        "worstHipsPosition": worst_hips,
        "tolerances": {"semanticRotationDegrees": 0.001, "hipsPositionSceneUnits": 1e-5},
    }
    return playback, {"canonical": root, "appliedScene": root_scene}


def _contact_diagnostics(armature, animation: dict, mapping: dict) -> dict:
    semantics = ("LeftFoot", "LeftToe", "RightFoot", "RightToe")
    joints = mapping["joints"]
    rest_heights = []
    for semantic in semantics:
        bone = armature.data.bones[joints[semantic]]
        rest_heights.extend((float((armature.matrix_world @ bone.head_local).z), float((armature.matrix_world @ bone.tail_local).z)))
    ground = min(rest_heights)
    rows = {}
    for semantic in semantics:
        points = []
        for sample in range(animation["frameCount"]):
            bpy.context.scene.frame_set(sample + 1)
            bpy.context.view_layer.update()
            bone = armature.pose.bones[joints[semantic]]
            point = armature.matrix_world @ bone.head
            points.append(point)
        min_height = min(float(point.z) for point in points)
        max_height = max(float(point.z) for point in points)
        planar = max(math.hypot(float(point.x - points[0].x), float(point.y - points[0].y)) for point in points)
        rows[semantic] = {"targetBone": joints[semantic], "minHeight": min_height, "maxHeight": max_height, "minimumRelativeToRestGround": min_height - ground, "maxPlanarTravelFromFirstSample": planar}
    penetration = min(row["minimumRelativeToRestGround"] for row in rows.values())
    return {
        "schema": "motion2sheet.humanoid-motion.diagnostics.contact",
        "version": 1,
        "acceptanceGate": False,
        "footIkApplied": False,
        "restGroundHeight": ground,
        "minimumGroundClearance": penetration,
        "groundPenetrationObserved": penetration < -1e-4,
        "note": "Foot sliding, floating and penetration are reported only; Humanoid Motion never stores source joint XYZ.",
        "joints": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    args = parser.parse_args(_argv())
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    output = Path(request["output"])
    diagnostics = output / "diagnostics"
    diagnostics.mkdir(parents=True, exist_ok=True)
    animation_path = Path(request["animationPath"])
    if _sha256(animation_path) != request["animationSha256"]:
        raise RuntimeError("Humanoid Motion animation SHA changed before Blender playback")
    animation = read_animation(animation_path)
    rig_path = Path(request["characterRigPath"])
    rig = validate_rig_document(read_json(rig_path))
    mapping = validate_character_mapping(read_mapping(Path(request["mappingPath"])), rig)
    skin = validate_skin_document(read_json(Path(request["skinPath"])), rig)

    model_path = Path(request["modelPath"])
    model_objects = import_geometry_glb(model_path)
    layout = mesh_layout(model_objects)
    verify_model_identity(skin, model_path, layout)
    model_identity = {
        "pass": True,
        "sameMeshObjects": sorted(row["object"] for row in layout) == sorted(mesh["object"] for mesh in skin["meshes"]),
        "sameVertexCounts": all(next(row for row in layout if row["object"] == mesh["object"])["vertexCount"] == mesh["vertexCount"] for mesh in skin["meshes"]),
        "sameVertexOrder": all(next(row for row in layout if row["object"] == mesh["object"])["vertexOrderHash"] == mesh["vertexOrderHash"] for mesh in skin["meshes"]),
        "meshCount": len(layout),
        "vertexCount": sum(row["vertexCount"] for row in layout),
        "layout": layout,
    }
    _write(diagnostics / "model_identity.json", model_identity)

    armature = build_armature(rig)
    reconstructed = reconstruct_skin(model_objects, armature, skin)
    skin_report = compare_skin_bindings(skin, reconstructed, tolerance=float(request["skinWeightTolerance"]))
    _write(diagnostics / "skin_reconstruction.json", skin_report)
    if not skin_report["pass"]:
        raise RuntimeError(f"Humanoid Motion skin reconstruction failed: {skin_report}")

    _action, runtime = _build_runtime_action(armature, animation, mapping)
    semantic_report = mapping_diagnostics(mapping, rig)
    semantic_report["characterId"] = rig["id"]
    _write(diagnostics / "semantic_mapping.json", semantic_report)
    retarget = {
        "schema": "motion2sheet.humanoid-motion.diagnostics.retarget",
        "version": 1,
        "runtimeTransformsDerived": True,
        "runtimeTransformsAreAnimationAuthority": False,
        "rotationFormula": "RtargetPose = Qroot * Dcanonical * RtargetRest",
        "translationFormula": "pHips = pRest + Qroot*(Ltarget*inPlaceHipsOffset); Humanoid Motion Root translation is zero",
        "rootApplication": "virtual Root yaw folded into semantic world rotations; Root translation remains zero",
        "helperPolicy": "deterministic rest-chain slerp",
        "targetMeanLegLengthSceneUnits": runtime["targetMeanLegLengthSceneUnits"],
        "bridgeHelpers": runtime["bridgeHelpers"],
        "joints": [
            {"canonicalSemantic": semantic, "targetBone": mapping["joints"][semantic], "targetRestWorldRotation": runtime["restWorldRotation"][semantic], "restCorrectionApplied": True}
            for semantic in MAPPED_JOINTS
        ],
    }
    _write(diagnostics / "retarget.json", retarget)
    playback, root_motion = _playback_diagnostics(armature, animation, mapping, rig, runtime)
    _write(diagnostics / "playback.json", playback)
    _write(diagnostics / "root_motion.json", root_motion)
    _write(diagnostics / "contact.json", _contact_diagnostics(armature, animation, mapping))
    if not playback["pass"]:
        raise RuntimeError(f"Humanoid Motion playback fidelity failed: {playback}")

    request["rootBone"] = mapping["joints"]["Hips"]
    setup_camera_and_render(request, armature)
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "runtime.blend"))
    if _sha256(animation_path) != request["animationSha256"]:
        raise RuntimeError("Humanoid Motion animation SHA changed during Blender playback")
    print(json.dumps({"characterId": rig["id"], "playback": playback, "rootMotion": root_motion}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
