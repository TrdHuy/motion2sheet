from __future__ import annotations

import copy
import math
from typing import Any

from .schema import (
    MAPPED_JOINTS,
    QUATERNION_CONTINUITY_TOLERANCE,
    QUATERNION_NORM_TOLERANCE,
    ROOT_TRANSLATION_TOLERANCE,
    validate_animation,
)

FPS_TOLERANCE = 1e-9
ROTATION_TOLERANCE_DEGREES = 0.005
HIPS_TRANSLATION_TOLERANCE = 1e-5
LOCOMOTION_DETECTION_TOLERANCE = 1e-4
SUPPORTED_INHERIT_SCALE = "FULL"


def _matrix_multiply(first: list[list[float]], second: list[list[float]]) -> list[list[float]]:
    return [
        [sum(first[row][k] * second[k][column] for k in range(4)) for column in range(4)]
        for row in range(4)
    ]


def _quaternion_normalize(value: list[float]) -> list[float]:
    norm = math.sqrt(sum(component * component for component in value))
    if not math.isfinite(norm) or norm <= 1e-15:
        raise ValueError("fidelity oracle encountered a zero/non-finite quaternion")
    return [component / norm for component in value]


def _quaternion_multiply(first: list[float], second: list[float]) -> list[float]:
    w, x, y, z = first
    sw, sx, sy, sz = second
    return [
        w * sw - x * sx - y * sy - z * sz,
        w * sx + x * sw + y * sz - z * sy,
        w * sy - x * sz + y * sw + z * sx,
        w * sz + x * sy - y * sx + z * sw,
    ]


def _quaternion_inverse(value: list[float]) -> list[float]:
    value = _quaternion_normalize(value)
    return [value[0], -value[1], -value[2], -value[3]]


def _quaternion_rotate(value: list[float], vector: list[float]) -> list[float]:
    rotated = _quaternion_multiply(
        _quaternion_multiply(_quaternion_normalize(value), [0.0, *vector]),
        _quaternion_inverse(value),
    )
    return rotated[1:]


def _rotation_error_degrees(first: list[float], second: list[float]) -> float:
    first = _quaternion_normalize(first)
    second = _quaternion_normalize(second)
    dot = min(1.0, abs(sum(a * b for a, b in zip(first, second))))
    return math.degrees(2.0 * math.acos(dot))


def _trs_matrix(transform: dict[str, Any]) -> list[list[float]]:
    w, x, y, z = _quaternion_normalize([float(value) for value in transform["rotationQuaternion"]])
    rotation = [
        [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
        [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
        [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
    ]
    scale = [float(value) for value in transform["scale"]]
    translation = [float(value) for value in transform["translation"]]
    result = [[0.0] * 4 for _ in range(4)]
    for row in range(3):
        for column in range(3):
            result[row][column] = rotation[row][column] * scale[column]
        result[row][3] = translation[row]
    result[3][3] = 1.0
    return result


def _matrix_rotation(matrix: list[list[float]]) -> list[float]:
    columns: list[list[float]] = []
    for column in range(3):
        axis = [matrix[row][column] for row in range(3)]
        length = math.sqrt(sum(value * value for value in axis))
        if length <= 1e-15:
            raise ValueError("fidelity oracle encountered a degenerate transform axis")
        columns.append([value / length for value in axis])
    shear = max(
        abs(sum(columns[first][row] * columns[second][row] for row in range(3)))
        for first in range(3)
        for second in range(first + 1, 3)
    )
    if shear > 1e-4:
        raise ValueError(f"fidelity oracle source world transform contains unsupported shear: {shear:.12g}")
    rotation = [[columns[column][row] for column in range(3)] for row in range(3)]
    trace = rotation[0][0] + rotation[1][1] + rotation[2][2]
    if trace > 0.0:
        size = math.sqrt(trace + 1.0) * 2.0
        quaternion = [0.25 * size, (rotation[2][1] - rotation[1][2]) / size, (rotation[0][2] - rotation[2][0]) / size, (rotation[1][0] - rotation[0][1]) / size]
    elif rotation[0][0] > rotation[1][1] and rotation[0][0] > rotation[2][2]:
        size = math.sqrt(1.0 + rotation[0][0] - rotation[1][1] - rotation[2][2]) * 2.0
        quaternion = [(rotation[2][1] - rotation[1][2]) / size, 0.25 * size, (rotation[0][1] + rotation[1][0]) / size, (rotation[0][2] + rotation[2][0]) / size]
    elif rotation[1][1] > rotation[2][2]:
        size = math.sqrt(1.0 + rotation[1][1] - rotation[0][0] - rotation[2][2]) * 2.0
        quaternion = [(rotation[0][2] - rotation[2][0]) / size, (rotation[0][1] + rotation[1][0]) / size, 0.25 * size, (rotation[1][2] + rotation[2][1]) / size]
    else:
        size = math.sqrt(1.0 + rotation[2][2] - rotation[0][0] - rotation[1][1]) * 2.0
        quaternion = [(rotation[1][0] - rotation[0][1]) / size, (rotation[0][2] + rotation[2][0]) / size, (rotation[1][2] + rotation[2][1]) / size, 0.25 * size]
    return _quaternion_normalize(quaternion)


def _matrix_position(matrix: list[list[float]]) -> list[float]:
    return [matrix[index][3] for index in range(3)]


def _transform_point(matrix: list[list[float]], point: list[float]) -> list[float]:
    return [sum(matrix[row][column] * float(point[column]) for column in range(3)) + matrix[row][3] for row in range(3)]


def _identity_transform() -> dict[str, list[float]]:
    return {"translation": [0.0, 0.0, 0.0], "rotationQuaternion": [1.0, 0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0]}


def _world_matrices(rig: dict[str, Any], pose: dict[str, dict[str, Any]]) -> dict[str, list[list[float]]]:
    bones = {bone["name"]: bone for bone in rig["bones"]}
    armature = _trs_matrix(rig["armatureObject"]["transform"])
    result: dict[str, list[list[float]]] = {}
    def resolve(name: str) -> list[list[float]]:
        if name in result:
            return result[name]
        bone = bones[name]
        local = _matrix_multiply(_trs_matrix(bone["rest"]), _trs_matrix(pose[name]))
        result[name] = _matrix_multiply(armature, local) if bone["parent"] is None else _matrix_multiply(resolve(bone["parent"]), local)
        return result[name]
    for name in bones:
        resolve(name)
    return result


def _validate_source_hierarchy_mode(rig: dict[str, Any], joints: dict[str, str]) -> None:
    bones = {bone["name"]: bone for bone in rig["bones"]}
    required: set[str] = set()
    for name in joints.values():
        current: str | None = name
        while current is not None:
            required.add(current)
            current = bones[current]["parent"]
    unsupported = []
    for name in sorted(required):
        properties = bones[name]["properties"]
        if not properties["useInheritRotation"] or not properties["useLocalLocation"] or properties["inheritScale"] != SUPPORTED_INHERIT_SCALE:
            unsupported.append(name)
    if unsupported:
        raise ValueError(f"fidelity oracle unsupported pose inheritance on source bones: {unsupported}")


def _mean_leg_length(rig: dict[str, Any], joints: dict[str, str]) -> float:
    bones = {bone["name"]: bone for bone in rig["bones"]}
    armature = _trs_matrix(rig["armatureObject"]["transform"])
    totals = []
    for side in ("Left", "Right"):
        total = 0.0
        for semantic in (f"{side}UpperLeg", f"{side}LowerLeg"):
            geometry = bones[joints[semantic]]["editGeometry"]
            head = _transform_point(armature, geometry["head"])
            tail = _transform_point(armature, geometry["tail"])
            total += math.dist(head, tail)
        totals.append(total)
    result = sum(totals) / 2.0
    if not math.isfinite(result) or result <= 1e-8:
        raise ValueError(f"fidelity oracle mean leg length is invalid: {result}")
    return result


def _yaw_twist(value: list[float]) -> list[float]:
    value = _quaternion_normalize(value)
    twist = [value[0], 0.0, 0.0, value[3]]
    norm = math.sqrt(twist[0] * twist[0] + twist[3] * twist[3])
    return [1.0, 0.0, 0.0, 0.0] if norm <= 1e-12 else [component / norm for component in twist]


def _quaternion_report(animation: dict[str, Any]) -> dict[str, Any]:
    tracks = {"Root": animation["root"]["rotations"], "Hips": animation["hips"]["rotations"], **{semantic: animation["joints"][semantic]["rotations"] for semantic in animation["joints"]}}
    maximum_norm_error = 0.0
    worst_norm = None
    minimum_adjacent_dot = 1.0
    worst_continuity = None
    sign_pass = True
    for semantic, track in tracks.items():
        previous = None
        for sample, raw in enumerate(track):
            norm_error = abs(math.sqrt(sum(float(value) ** 2 for value in raw)) - 1.0)
            if norm_error > maximum_norm_error:
                maximum_norm_error = norm_error
                worst_norm = {"sample": sample, "semantic": semantic}
            first = next((float(value) for value in raw if abs(float(value)) > 1e-15), 0.0)
            if previous is None:
                sign_pass = sign_pass and first >= 0.0
            else:
                dot = sum(float(a) * float(b) for a, b in zip(previous, raw))
                if dot < minimum_adjacent_dot:
                    minimum_adjacent_dot = dot
                    worst_continuity = {"sample": sample, "semantic": semantic}
                sign_pass = sign_pass and (dot >= -QUATERNION_CONTINUITY_TOLERANCE and (abs(dot) > QUATERNION_CONTINUITY_TOLERANCE or first >= 0.0))
            previous = raw
    return {"pass": maximum_norm_error <= QUATERNION_NORM_TOLERANCE and sign_pass, "maxNormError": maximum_norm_error, "worstNorm": worst_norm, "minimumAdjacentDot": minimum_adjacent_dot, "worstContinuity": worst_continuity, "signContinuityPass": sign_pass, "tolerances": {"norm": QUATERNION_NORM_TOLERANCE, "continuityDot": QUATERNION_CONTINUITY_TOLERANCE}}


def compare_source_to_humanoid_motion(source_rig: dict[str, Any], source_animation: dict[str, Any], mapping: dict[str, Any], humanoid_motion: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    try:
        animation = validate_animation(copy.deepcopy(humanoid_motion))
    except (KeyError, TypeError, ValueError) as exc:
        return {"schema": "motion2sheet.humanoid-motion.source-fidelity", "version": 1, "pass": False, "independentPath": "pure-python Contract B hierarchy/TRS evaluation; no Humanoid Motion exporter or playback imports", "schemaValidation": {"pass": False, "error": str(exc)}, "failures": [f"Humanoid Motion schema validation failed: {exc}"]}

    joints = mapping["joints"]
    _validate_source_hierarchy_mode(source_rig, joints)
    frames = source_animation["frames"]
    frame_count_pass = animation["frameCount"] == source_animation["frameCount"] == len(frames)
    comparison_count = min(animation["frameCount"], len(frames))
    fps_error = abs(float(animation["fps"]) - float(source_animation["fps"]))
    if not frame_count_pass:
        failures.append("frameCount does not match the Contract B source")
    if fps_error > FPS_TOLERANCE:
        failures.append("FPS does not match the Contract B source")

    identities = {bone["name"]: _identity_transform() for bone in source_rig["bones"]}
    rest_world = _world_matrices(source_rig, identities)
    rest_rotations = {semantic: _matrix_rotation(rest_world[name]) for semantic, name in joints.items()}
    hips_name = joints["Hips"]
    hips_rest_position = _matrix_position(rest_world[hips_name])
    leg_length = _mean_leg_length(source_rig, joints)
    source_world = [_world_matrices(source_rig, row["bones"]) for row in frames]
    hips_positions = [_matrix_position(world[hips_name]) for world in source_world]
    hips_rotations = [_matrix_rotation(world[hips_name]) for world in source_world]
    first_hips_rotation = hips_rotations[0]
    source_offsets = [[(position[index] - hips_rest_position[index]) / leg_length for index in range(3)] for position in hips_positions]
    planar_end_to_end = [source_offsets[-1][0] - source_offsets[0][0], source_offsets[-1][1] - source_offsets[0][1], 0.0]
    planar_displacement = math.hypot(planar_end_to_end[0], planar_end_to_end[1])

    max_root_rotation_error = 0.0
    worst_root_rotation = None
    max_semantic_rotation_error = 0.0
    worst_semantic_rotation = None
    semantic_maxima = {semantic: 0.0 for semantic in MAPPED_JOINTS}
    max_hips_translation_error = 0.0
    worst_hips_translation = None
    expected_vertical: list[float] = []
    actual_vertical: list[float] = []

    for sample, (source_frame, world, hips_rotation, source_offset) in enumerate(zip(frames[:comparison_count], source_world[:comparison_count], hips_rotations[:comparison_count], source_offsets[:comparison_count])):
        progress = sample / (len(frames) - 1) if len(frames) > 1 else 0.0
        stripped = [planar_end_to_end[0] * progress, planar_end_to_end[1] * progress, 0.0]
        expected_root_rotation = _yaw_twist(_quaternion_multiply(hips_rotation, _quaternion_inverse(first_hips_rotation)))
        root_error = _rotation_error_degrees(expected_root_rotation, animation["root"]["rotations"][sample])
        if root_error > max_root_rotation_error:
            max_root_rotation_error = root_error
            worst_root_rotation = {"sample": sample, "sourceFrame": source_frame["frame"]}
        expected_hips = _quaternion_rotate(_quaternion_inverse(expected_root_rotation), [source_offset[index] - stripped[index] for index in range(3)])
        actual_hips = animation["hips"]["translations"][sample] if animation["hips"]["translations"] else [0.0, 0.0, 0.0]
        hips_error = math.dist(expected_hips, actual_hips)
        if hips_error > max_hips_translation_error:
            max_hips_translation_error = hips_error
            worst_hips_translation = {"sample": sample, "sourceFrame": source_frame["frame"]}
        expected_vertical.append(expected_hips[2])
        actual_vertical.append(float(actual_hips[2]))
        for semantic, bone_name in joints.items():
            expected_rotation = _quaternion_normalize(_quaternion_multiply(_quaternion_multiply(_quaternion_inverse(expected_root_rotation), _matrix_rotation(world[bone_name])), _quaternion_inverse(rest_rotations[semantic])))
            actual_rotation = animation["hips"]["rotations"][sample] if semantic == "Hips" else animation["joints"][semantic]["rotations"][sample]
            error = _rotation_error_degrees(expected_rotation, actual_rotation)
            semantic_maxima[semantic] = max(semantic_maxima[semantic], error)
            if error > max_semantic_rotation_error:
                max_semantic_rotation_error = error
                worst_semantic_rotation = {"sample": sample, "sourceFrame": source_frame["frame"], "semantic": semantic, "sourceBone": bone_name}

    translations = animation["root"]["translations"]
    root_magnitudes = [math.sqrt(sum(component * component for component in row)) for row in translations]
    root_max_magnitude = max(root_magnitudes)
    root_max_abs = max(abs(component) for row in translations for component in row)
    root_worst = root_magnitudes.index(root_max_magnitude)
    root_pass = root_max_abs <= ROOT_TRANSLATION_TOLERANCE
    if not root_pass:
        failures.append("Humanoid Motion Root translation is not in-place")
    if max_root_rotation_error > ROTATION_TOLERANCE_DEGREES:
        failures.append("Root yaw does not match independent source semantics")
    if max_semantic_rotation_error > ROTATION_TOLERANCE_DEGREES:
        failures.append("one or more semantic rotations do not match the source")
    if max_hips_translation_error > HIPS_TRANSLATION_TOLERANCE:
        failures.append("Hips residual translation does not match in-place source semantics")
    quaternion = _quaternion_report(animation)
    if not quaternion["pass"]:
        failures.append("quaternion validity/continuity failed")

    left_right_pairs = []
    for suffix in ("Shoulder", "UpperArm", "LowerArm", "Hand", "UpperLeg", "LowerLeg", "Foot", "Toe"):
        left_semantic, right_semantic = f"Left{suffix}", f"Right{suffix}"
        left_x = _matrix_position(rest_world[joints[left_semantic]])[0]
        right_x = _matrix_position(rest_world[joints[right_semantic]])[0]
        pair_pass = joints[left_semantic] != joints[right_semantic] and left_x > right_x + 1e-6 and semantic_maxima[left_semantic] <= ROTATION_TOLERANCE_DEGREES and semantic_maxima[right_semantic] <= ROTATION_TOLERANCE_DEGREES
        left_right_pairs.append({"semanticPair": suffix, "leftBone": joints[left_semantic], "rightBone": joints[right_semantic], "leftX": left_x, "rightX": right_x, "pass": pair_pass})
    left_right_pass = all(row["pass"] for row in left_right_pairs)
    if not left_right_pass:
        failures.append("left/right semantic identity failed")

    expected_vertical_range = max(expected_vertical) - min(expected_vertical)
    actual_vertical_range = max(actual_vertical) - min(actual_vertical)
    locomotion_pass = root_pass and max_hips_translation_error <= HIPS_TRANSLATION_TOLERANCE
    if not locomotion_pass:
        failures.append("source locomotion stripping verification failed")

    return {
        "schema": "motion2sheet.humanoid-motion.source-fidelity", "version": 1, "pass": not failures,
        "independentPath": "pure-python Contract B hierarchy/TRS evaluation; no Humanoid Motion exporter or playback imports",
        "schemaValidation": {"pass": True},
        "source": {"rigId": source_rig["id"], "animationId": source_animation["id"], "frameCount": source_animation["frameCount"], "fps": source_animation["fps"], "meanLegLengthSceneUnits": leg_length},
        "humanoidMotion": {"animationId": animation["id"], "frameCount": animation["frameCount"], "fps": animation["fps"]},
        "tolerances": {"fps": FPS_TOLERANCE, "rotationDegrees": ROTATION_TOLERANCE_DEGREES, "hipsTranslationMeanLegLength": HIPS_TRANSLATION_TOLERANCE, "rootTranslationMeanLegLength": ROOT_TRANSLATION_TOLERANCE},
        "timing": {"pass": frame_count_pass and fps_error <= FPS_TOLERANCE, "fpsError": fps_error},
        "maxErrors": {"rootRotationDegrees": max_root_rotation_error, "semanticRotationDegrees": max_semantic_rotation_error, "hipsTranslationMeanLegLength": max_hips_translation_error, "rootTranslationMeanLegLength": root_max_abs},
        "worstRootRotation": worst_root_rotation, "worstSemantic": worst_semantic_rotation, "worstHipsTranslation": worst_hips_translation,
        "semanticRotationMaximaDegrees": semantic_maxima,
        "rootInvariant": {"pass": root_pass, "tolerance": ROOT_TRANSLATION_TOLERANCE, "maxAbsComponent": root_max_abs, "maxMagnitude": root_max_magnitude, "worstFrame": root_worst},
        "locomotionStripping": {"pass": locomotion_pass, "policy": "linear-endpoint-planar-detrend-v1", "sourcePlanarEndToEnd": planar_end_to_end, "sourcePlanarDisplacement": planar_displacement, "sourceHadPlanarLocomotion": planar_displacement > LOCOMOTION_DETECTION_TOLERANCE, "detectionTolerance": LOCOMOTION_DETECTION_TOLERANCE, "strippedPlanarEndToEnd": planar_end_to_end, "expectedHipsVerticalRange": expected_vertical_range, "actualHipsVerticalRange": actual_vertical_range, "verticalRangeError": abs(expected_vertical_range - actual_vertical_range)},
        "leftRightVerification": {"pass": left_right_pass, "rightAxis": "+X", "pairs": left_right_pairs},
        "quaternionVerification": quaternion,
        "failures": failures,
    }
