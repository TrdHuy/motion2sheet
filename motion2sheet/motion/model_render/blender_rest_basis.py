from __future__ import annotations

import math
from typing import Any

import bpy
from mathutils import Matrix, Quaternion, Vector

from motion2sheet.motion.roundtrip.blender_common import ordered_bones


ROTATION_FIDELITY_TOLERANCE_DEGREES = 0.001
JOINT_POSITION_FIDELITY_TOLERANCE = 1e-4
SCALE_FIDELITY_TOLERANCE = 1e-5
ROOT_DIRECTION_TOLERANCE_DEGREES = 0.001
ROOT_DISPLACEMENT_TOLERANCE = 1e-5


def _matrix3_rows(matrix: Matrix) -> list[list[float]]:
    value = matrix.to_3x3()
    return [[float(value[row][column]) for column in range(3)] for row in range(3)]


def _vector3(value: Vector) -> list[float]:
    return [float(value[index]) for index in range(3)]


def _canonical_quaternion(value: Quaternion) -> Quaternion:
    result = value.normalized()
    components = [float(result.w), float(result.x), float(result.y), float(result.z)]
    sign = 1.0
    for component in components:
        if abs(component) <= 1e-15:
            continue
        if component < 0.0:
            sign = -1.0
        break
    if sign < 0.0:
        result = Quaternion((-result.w, -result.x, -result.y, -result.z))
    return result


def _local_rest_matrix(armature: bpy.types.Object, bone_name: str) -> Matrix:
    bone = armature.data.bones[bone_name]
    if bone.parent is None:
        return bone.matrix_local.copy()
    return bone.parent.matrix_local.inverted_safe() @ bone.matrix_local


def _local_pose_matrix(armature: bpy.types.Object, bone_name: str) -> Matrix:
    pose_bone = armature.pose.bones[bone_name]
    if pose_bone.parent is None:
        return pose_bone.matrix.copy()
    return pose_bone.parent.matrix.inverted_safe() @ pose_bone.matrix


def _rotation_error_degrees(first: Quaternion, second: Quaternion) -> float:
    return math.degrees(first.normalized().rotation_difference(second.normalized()).angle)


def _direction_error_degrees(first: Vector, second: Vector) -> float:
    if first.length <= 1e-12 or second.length <= 1e-12:
        return 0.0 if first.length <= 1e-12 and second.length <= 1e-12 else 180.0
    return math.degrees(first.angle(second))


def _component_scale_ratio(source: Vector, rest: Vector) -> Vector:
    values = []
    for index in range(3):
        denominator = float(rest[index])
        if abs(denominator) <= 1e-12:
            raise RuntimeError("rest-basis adaptation encountered a zero rest scale component")
        values.append(float(source[index]) / denominator)
    return Vector(values)


def _component_multiply(first: Vector, second: Vector) -> Vector:
    return Vector(tuple(float(first[index]) * float(second[index]) for index in range(3)))


def build_static_rest_basis_adapter(
    source_armature: bpy.types.Object,
    target_armature: bpy.types.Object,
) -> dict[str, Any]:
    """Build static exact-name basis maps using rest data only.

    No Action, current frame, pose channel, or animation sample participates here.
    The reported B_target_from_source changes coordinates for rest-relative rotation
    deltas from the source bone basis into the target bone basis:

        targetDelta = B_target_from_source * sourceDelta * inverse(B_target_from_source)
    """

    source_names = set(source_armature.data.bones.keys())
    target_names = set(target_armature.data.bones.keys())
    if source_names != target_names:
        raise RuntimeError("rest-basis adapter requires exact bone names")

    rows: dict[str, Any] = {}
    max_head = max_tail = max_length = 0.0
    worst_head = worst_tail = worst_length = None
    for bone in ordered_bones(source_armature):
        name = bone.name
        source_bone = source_armature.data.bones[name]
        target_bone = target_armature.data.bones[name]
        source_parent = source_bone.parent.name if source_bone.parent else None
        target_parent = target_bone.parent.name if target_bone.parent else None
        if source_parent != target_parent:
            raise RuntimeError(f"rest-basis adapter requires exact hierarchy for {name}")

        source_local = _local_rest_matrix(source_armature, name)
        target_local = _local_rest_matrix(target_armature, name)
        _source_location, source_rotation, _source_scale = source_local.decompose()
        _target_location, target_rotation, _target_scale = target_local.decompose()
        basis = target_rotation.to_matrix().inverted_safe() @ source_rotation.to_matrix()
        basis_quaternion = _canonical_quaternion(basis.to_quaternion())

        source_head = source_bone.head_local
        source_tail = source_bone.tail_local
        target_head = target_bone.head_local
        target_tail = target_bone.tail_local
        head_error = (source_head - target_head).length
        tail_error = (source_tail - target_tail).length
        length_error = abs(float(source_bone.length) - float(target_bone.length))
        if head_error > max_head:
            max_head, worst_head = head_error, name
        if tail_error > max_tail:
            max_tail, worst_tail = tail_error, name
        if length_error > max_length:
            max_length, worst_length = length_error, name

        rows[name] = {
            "parent": source_parent,
            "B_target_from_source": _matrix3_rows(basis),
            "B_target_from_sourceQuaternion": [
                float(basis_quaternion.w),
                float(basis_quaternion.x),
                float(basis_quaternion.y),
                float(basis_quaternion.z),
            ],
            "sourceRestLocalRotation": [
                float(_canonical_quaternion(source_rotation).w),
                float(_canonical_quaternion(source_rotation).x),
                float(_canonical_quaternion(source_rotation).y),
                float(_canonical_quaternion(source_rotation).z),
            ],
            "targetRestLocalRotation": [
                float(_canonical_quaternion(target_rotation).w),
                float(_canonical_quaternion(target_rotation).x),
                float(_canonical_quaternion(target_rotation).y),
                float(_canonical_quaternion(target_rotation).z),
            ],
        }

    return {
        "schema": "motion2sheet.diagnostics.rest-basis-adapter",
        "version": 1,
        "adaptationType": "rest-basis",
        "boneCount": len(rows),
        "boneMapping": "exact-name",
        "exactHierarchyRequired": True,
        "sameCoordinateConventionRequired": True,
        "fuzzyMapping": False,
        "semanticGuessing": False,
        "topologyConversion": False,
        "helperBoneSolver": False,
        "derivedFrom": ["animation_rig.rest", "character_rig.rest"],
        "animationFramesRead": False,
        "frameDependent": False,
        "formula": "targetDelta = B_target_from_source * sourceDelta * inverse(B_target_from_source)",
        "translationPolicy": "preserve source parent-space rest-relative translation delta; root therefore preserves armature-space locomotion delta",
        "scalePolicy": "preserve source local scale ratio relative to source rest and apply it to target rest scale",
        "restGeometryDifference": {
            "maxHeadPositionError": max_head,
            "worstHeadBone": worst_head,
            "maxTailPositionError": max_tail,
            "worstTailBone": worst_tail,
            "maxBoneLengthError": max_length,
            "worstLengthBone": worst_length,
        },
        "bones": rows,
    }


def build_rest_basis_adapted_action(
    source_armature: bpy.types.Object,
    target_armature: bpy.types.Object,
    animation: dict[str, Any],
    static_adapter: dict[str, Any],
):
    """Derive a runtime target Action from immutable Contract B + source/target rest.

    The canonical animation document is never changed. Source Contract B is first
    evaluated on its own source rest armature. For each frame/bone, the source pose is
    converted to a rest-relative parent-space motion operator and applied to the target
    rest. Translation and scale follow the explicit policies reported above.
    """

    if static_adapter.get("animationFramesRead") is not False or static_adapter.get("frameDependent") is not False:
        raise RuntimeError("rest-basis adapter must be static before runtime motion derivation")
    scene = bpy.context.scene
    start, end = animation["frameRange"]
    scene.render.fps = int(animation["fpsNumerator"])
    scene.render.fps_base = float(animation["fpsBase"])
    scene.frame_start = int(start)
    scene.frame_end = int(end)
    action = bpy.data.actions.new(f"{animation['source']['action']}__M2S_LEVEL2_REST_BASIS")
    target_armature.animation_data_create().action = action
    for pose_bone in target_armature.pose.bones:
        pose_bone.rotation_mode = "QUATERNION"

    target_order = [bone.name for bone in ordered_bones(target_armature)]
    source_names = set(source_armature.pose.bones.keys())
    if set(target_order) != source_names:
        raise RuntimeError("Level-2 runtime action requires exact source/target bone names")

    for entry in animation["frames"]:
        frame = int(entry["frame"])
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        desired_armature: dict[str, Matrix] = {}
        for name in target_order:
            source_local_rest = _local_rest_matrix(source_armature, name)
            target_local_rest = _local_rest_matrix(target_armature, name)
            source_local_pose = _local_pose_matrix(source_armature, name)

            source_rest_location, source_rest_rotation, source_rest_scale = source_local_rest.decompose()
            target_rest_location, target_rest_rotation, target_rest_scale = target_local_rest.decompose()
            source_pose_location, source_pose_rotation, source_pose_scale = source_local_pose.decompose()

            parent_space_rotation_delta = source_pose_rotation @ source_rest_rotation.inverted()
            target_pose_rotation = _canonical_quaternion(parent_space_rotation_delta @ target_rest_rotation)
            parent_space_translation_delta = source_pose_location - source_rest_location
            target_pose_location = target_rest_location + parent_space_translation_delta
            source_scale_ratio = _component_scale_ratio(source_pose_scale, source_rest_scale)
            target_pose_scale = _component_multiply(target_rest_scale, source_scale_ratio)
            target_local_pose = Matrix.LocRotScale(target_pose_location, target_pose_rotation, target_pose_scale)

            parent_name = target_armature.data.bones[name].parent.name if target_armature.data.bones[name].parent else None
            target_pose_matrix = target_local_pose if parent_name is None else desired_armature[parent_name] @ target_local_pose
            desired_armature[name] = target_pose_matrix
            target_pose_bone = target_armature.pose.bones[name]
            target_pose_bone.matrix = target_pose_matrix
            bpy.context.view_layer.update()

            location, rotation, scale = target_pose_bone.matrix_basis.decompose()
            target_pose_bone.location = location
            target_pose_bone.rotation_quaternion = _canonical_quaternion(rotation)
            target_pose_bone.scale = scale
            target_pose_bone.keyframe_insert(data_path="location", frame=frame, group=name)
            target_pose_bone.keyframe_insert(data_path="rotation_quaternion", frame=frame, group=name)
            target_pose_bone.keyframe_insert(data_path="scale", frame=frame, group=name)

    for fcurve in action.fcurves:
        for keyframe in fcurve.keyframe_points:
            keyframe.interpolation = "LINEAR"
    scene.frame_set(int(start))
    bpy.context.view_layer.update()
    return action


def rest_basis_motion_fidelity(
    source_armature: bpy.types.Object,
    target_armature: bpy.types.Object,
    animation: dict[str, Any],
    root_bone: str,
    static_adapter: dict[str, Any],
) -> dict[str, Any]:
    """Compare every evaluated source/target frame after Level-2 adaptation.

    Rotation fidelity compares world-space *motion operators normalized by each rig's
    own static rest basis*. Raw world pose-basis difference is also reported so a real
    rest-basis distinction is never hidden. Joint positions are compared directly.
    """

    frames = [int(row["frame"]) for row in animation["frames"]]
    names = [bone.name for bone in ordered_bones(source_armature)]
    if set(names) != set(target_armature.pose.bones.keys()):
        raise RuntimeError("Level-2 fidelity requires exact source/target bone names")

    max_motion_rotation = max_raw_rotation = max_joint = max_translation = max_scale = 0.0
    worst_motion_rotation = worst_raw_rotation = worst_joint = worst_translation = worst_scale = None
    source_root_positions: list[Vector] = []
    target_root_positions: list[Vector] = []

    source_world_rest_rotation: dict[str, Quaternion] = {}
    target_world_rest_rotation: dict[str, Quaternion] = {}
    for name in names:
        source_world_rest = source_armature.matrix_world @ source_armature.data.bones[name].matrix_local
        target_world_rest = target_armature.matrix_world @ target_armature.data.bones[name].matrix_local
        source_world_rest_rotation[name] = source_world_rest.to_quaternion().normalized()
        target_world_rest_rotation[name] = target_world_rest.to_quaternion().normalized()

    for frame in frames:
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        for name in names:
            source_pose = source_armature.matrix_world @ source_armature.pose.bones[name].matrix
            target_pose = target_armature.matrix_world @ target_armature.pose.bones[name].matrix
            source_location, source_rotation, source_scale = source_pose.decompose()
            target_location, target_rotation, target_scale = target_pose.decompose()

            source_motion_rotation = source_rotation @ source_world_rest_rotation[name].inverted()
            target_motion_rotation = target_rotation @ target_world_rest_rotation[name].inverted()
            motion_rotation_error = _rotation_error_degrees(source_motion_rotation, target_motion_rotation)
            raw_rotation_error = _rotation_error_degrees(source_rotation, target_rotation)
            translation_error = (source_location - target_location).length
            scale_error = max(abs(float(source_scale[index]) - float(target_scale[index])) for index in range(3))

            source_bone = source_armature.pose.bones[name]
            target_bone = target_armature.pose.bones[name]
            source_head = source_armature.matrix_world @ source_bone.head
            source_tail = source_armature.matrix_world @ source_bone.tail
            target_head = target_armature.matrix_world @ target_bone.head
            target_tail = target_armature.matrix_world @ target_bone.tail
            head_error = (source_head - target_head).length
            tail_error = (source_tail - target_tail).length
            joint_error = max(head_error, tail_error)

            location = {"frame": frame, "bone": name}
            if motion_rotation_error > max_motion_rotation:
                max_motion_rotation, worst_motion_rotation = motion_rotation_error, location
            if raw_rotation_error > max_raw_rotation:
                max_raw_rotation, worst_raw_rotation = raw_rotation_error, location
            if joint_error > max_joint:
                max_joint, worst_joint = joint_error, {**location, "headError": head_error, "tailError": tail_error}
            if translation_error > max_translation:
                max_translation, worst_translation = translation_error, location
            if scale_error > max_scale:
                max_scale, worst_scale = scale_error, location

        if frame in (frames[0], frames[-1]):
            source_root_positions.append(source_armature.matrix_world @ source_armature.pose.bones[root_bone].head)
            target_root_positions.append(target_armature.matrix_world @ target_armature.pose.bones[root_bone].head)

    source_delta = source_root_positions[-1] - source_root_positions[0]
    target_delta = target_root_positions[-1] - target_root_positions[0]
    source_displacement = source_delta.length
    target_displacement = target_delta.length
    root_direction_error = _direction_error_degrees(source_delta, target_delta)
    root_displacement_error = abs(source_displacement - target_displacement)
    names_ok = set(source_armature.pose.bones.keys()) == set(target_armature.pose.bones.keys()) == set(names)

    motion_equivalent = (
        max_motion_rotation <= ROTATION_FIDELITY_TOLERANCE_DEGREES
        and max_scale <= SCALE_FIDELITY_TOLERANCE
        and root_direction_error <= ROOT_DIRECTION_TOLERANCE_DEGREES
        and root_displacement_error <= ROOT_DISPLACEMENT_TOLERANCE
        and names_ok
    )
    world_joint_equivalent = max_joint <= JOINT_POSITION_FIDELITY_TOLERANCE
    passed = motion_equivalent and world_joint_equivalent
    return {
        "pass": passed,
        "compatibilityLevel": 2,
        "adaptationApplied": True,
        "adaptationType": "rest-basis",
        "frameCount": len(frames),
        "boneCount": len(names),
        "leftRightIdentityPass": names_ok,
        "fullBonePlayback": names_ok,
        "motionAuthority": "animation.json",
        "runtimeTransformsDerivedFrom": ["animation_rig.json", "animation.json", "character_rig.json"],
        "derivedRuntimeTransformsAreMotionAuthority": False,
        "maxWorldMotionRotationErrorDegrees": max_motion_rotation,
        "worstWorldMotionRotation": worst_motion_rotation,
        "maxRawWorldPoseRotationDifferenceDegrees": max_raw_rotation,
        "worstRawWorldPoseRotationDifference": worst_raw_rotation,
        "maxWorldJointPositionError": max_joint,
        "worstWorldJointPosition": worst_joint,
        "maxWorldTranslationError": max_translation,
        "worstWorldTranslation": worst_translation,
        "maxWorldScaleError": max_scale,
        "worstWorldScale": worst_scale,
        "motionEquivalent": motion_equivalent,
        "worldJointEquivalent": world_joint_equivalent,
        "tolerances": {
            "worldMotionRotationDegrees": ROTATION_FIDELITY_TOLERANCE_DEGREES,
            "worldJointPosition": JOINT_POSITION_FIDELITY_TOLERANCE,
            "worldScale": SCALE_FIDELITY_TOLERANCE,
            "rootDirectionDegrees": ROOT_DIRECTION_TOLERANCE_DEGREES,
            "rootDisplacement": ROOT_DISPLACEMENT_TOLERANCE,
        },
        "rootMotion": {
            "sourceStart": _vector3(source_root_positions[0]),
            "sourceEnd": _vector3(source_root_positions[-1]),
            "sourceDelta": _vector3(source_delta),
            "sourceDisplacement": float(source_displacement),
            "targetStart": _vector3(target_root_positions[0]),
            "targetEnd": _vector3(target_root_positions[-1]),
            "targetDelta": _vector3(target_delta),
            "targetDisplacement": float(target_displacement),
            "directionErrorDegrees": root_direction_error,
            "displacementError": root_displacement_error,
            "directionPreserved": root_direction_error <= ROOT_DIRECTION_TOLERANCE_DEGREES,
            "displacementPreserved": root_displacement_error <= ROOT_DISPLACEMENT_TOLERANCE,
        },
        "restGeometryDifference": static_adapter["restGeometryDifference"],
        "rawWorldPoseRotationDifferenceIsAcceptanceGate": False,
        "note": "If world joint equivalence fails while rest-normalized motion rotation remains precise, the rigs differ in actual rest geometry/proportions rather than only coordinate basis.",
    }
