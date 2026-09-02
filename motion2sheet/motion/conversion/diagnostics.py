from __future__ import annotations

import math

from .math3d import clean, clean_vec, dot, length, mul3, mul3v, rotation4, unit
from .retarget import source_direction_descriptor, target_direction_descriptor

ACCEPTANCE_SEMANTICS = (
    "root", "pelvis", "head", "leftElbow", "leftWrist", "rightElbow", "rightWrist",
    "leftKnee", "leftAnkle", "rightKnee", "rightAnkle",
)
VISUAL_SEMANTICS = (
    "root", "pelvis", "head", "leftShoulder", "leftElbow", "leftWrist",
    "rightShoulder", "rightElbow", "rightWrist", "leftHip", "leftKnee", "leftAnkle",
    "rightHip", "rightKnee", "rightAnkle",
)
SEGMENTS = {
    "leftUpperArm": "LeftUpperArm", "leftForeArm": "LeftForeArm",
    "rightUpperArm": "RightUpperArm", "rightForeArm": "RightForeArm",
    "leftThigh": "LeftThigh", "leftShin": "LeftShin",
    "rightThigh": "RightThigh", "rightShin": "RightShin",
}
BENDS = {
    "leftElbow": ("LeftUpperArm", "LeftForeArm", "elbowBendDegrees"),
    "rightElbow": ("RightUpperArm", "RightForeArm", "elbowBendDegrees"),
    "leftKnee": ("LeftThigh", "LeftShin", "kneeBendDegrees"),
    "rightKnee": ("RightThigh", "RightShin", "kneeBendDegrees"),
}


def _distance(a, b) -> float:
    return math.sqrt(sum((float(a[i]) - float(b[i])) ** 2 for i in range(3)))


def _angle_degrees(a, b) -> float:
    ua, ub = unit(tuple(a), "direction A"), unit(tuple(b), "direction B")
    cosine = max(-1.0, min(1.0, dot(ua, ub)))
    return math.degrees(math.acos(cosine))


def _bone_y(rotation) -> tuple[float, float, float]:
    return rotation[0][1], rotation[1][1], rotation[2][1]


def _source_bone_direction(retargeted: dict, frame: dict, mapping: dict, target_name: str, *, rest: bool) -> tuple[float, float, float]:
    source_name = mapping["targetToSource"][target_name]
    matrix = retargeted["sourceRestWorld"][source_name] if rest else frame["sourcePose"][source_name]
    direction = _bone_y(rotation4(matrix))
    return mul3v(mapping["sourceToTargetAxes"], direction)


def _target_bone_direction(retargeted: dict, frame: dict, target_name: str, *, rest: bool) -> tuple[float, float, float]:
    matrix = retargeted["targetRests"][target_name].matrix if rest else frame["pose"][target_name]
    return _bone_y(rotation4(matrix))


def _bend_delta(retargeted: dict, frame: dict, mapping: dict, upper: str, lower: str, *, source: bool) -> float:
    if source:
        pose_angle = _angle_degrees(_source_bone_direction(retargeted, frame, mapping, upper, rest=False), _source_bone_direction(retargeted, frame, mapping, lower, rest=False))
        rest_angle = _angle_degrees(_source_bone_direction(retargeted, frame, mapping, upper, rest=True), _source_bone_direction(retargeted, frame, mapping, lower, rest=True))
    else:
        pose_angle = _angle_degrees(_target_bone_direction(retargeted, frame, upper, rest=False), _target_bone_direction(retargeted, frame, lower, rest=False))
        rest_angle = _angle_degrees(_target_bone_direction(retargeted, frame, upper, rest=True), _target_bone_direction(retargeted, frame, lower, rest=True))
    return pose_angle - rest_angle


def _normalized_wrist_height(points: dict, side: str) -> float:
    pelvis_z = float(points["pelvis"][2])
    head_z = float(points["head"][2])
    span = head_z - pelvis_z
    if abs(span) <= 1e-8:
        raise ValueError("pelvis/head vertical span is degenerate while evaluating retarget ordering")
    return (float(points[f"{side}Wrist"][2]) - pelvis_z) / span


def source_retarget_fidelity(retargeted: dict, mapping: dict) -> dict:
    tolerance = mapping["semanticRetargetTolerance"]
    per_segment = {name: {"maxErrorDegrees": 0.0, "worstFrame": None} for name in SEGMENTS}
    per_joint = {name: {"maxErrorDegrees": 0.0, "worstFrame": None} for name in BENDS}
    max_arm_direction = (0.0, None, None)
    max_leg_direction = (0.0, None, None)
    max_elbow = (0.0, None, None)
    max_knee = (0.0, None, None)
    max_root_direction = (0.0, None)
    max_vertical = (0.0, None, None)
    ordering_mismatches: list[dict] = []
    left_right_failures: list[dict] = []
    rows = []

    def update_max(current, value, frame, semantic):
        return (value, frame, semantic) if value > current[0] else current

    for index, frame in enumerate(retargeted["frames"], start=1):
        segment_errors = {}
        for semantic, target_name in SEGMENTS.items():
            source_descriptor = source_direction_descriptor(frame["sourcePose"], retargeted["sourceRestWorld"], mapping, target_name)
            target_descriptor = target_direction_descriptor(frame["pose"], retargeted["targetRests"], mapping, target_name)
            error = _angle_degrees(source_descriptor, target_descriptor)
            segment_errors[semantic] = clean(error, 9)
            if error > per_segment[semantic]["maxErrorDegrees"]:
                per_segment[semantic] = {"maxErrorDegrees": clean(error, 9), "worstFrame": index}
            if "Arm" in semantic or "ForeArm" in semantic:
                max_arm_direction = update_max(max_arm_direction, error, index, semantic)
            else:
                max_leg_direction = update_max(max_leg_direction, error, index, semantic)

        bend_errors = {}
        for semantic, (upper, lower, tolerance_key) in BENDS.items():
            source_delta = _bend_delta(retargeted, frame, mapping, upper, lower, source=True)
            target_delta = _bend_delta(retargeted, frame, mapping, upper, lower, source=False)
            error = abs(source_delta - target_delta)
            bend_errors[semantic] = {"sourceDeltaDegrees": clean(source_delta, 9), "targetDeltaDegrees": clean(target_delta, 9), "errorDegrees": clean(error, 9)}
            if error > per_joint[semantic]["maxErrorDegrees"]:
                per_joint[semantic] = {"maxErrorDegrees": clean(error, 9), "worstFrame": index}
            if tolerance_key == "elbowBendDegrees":
                max_elbow = update_max(max_elbow, error, index, semantic)
            else:
                max_knee = update_max(max_knee, error, index, semantic)

        source_root = frame["sourceRootDelta"]
        target_root = frame["rootTranslation"]
        if length(source_root) > 1e-8 and length(target_root) > 1e-8:
            root_error = _angle_degrees(source_root, target_root)
            if root_error > max_root_direction[0]:
                max_root_direction = (root_error, index)
        elif length(source_root) > 1e-8 or length(target_root) > 1e-8:
            root_error = 180.0
            if root_error > max_root_direction[0]:
                max_root_direction = (root_error, index)
        else:
            root_error = 0.0

        source_points = frame["sourceSemantics"]
        target_points = frame["semantics"]
        frame_ordering = {}
        for side in ("left", "right"):
            checks = {
                f"{side}WristBelowShoulder": (float(source_points[f"{side}Wrist"][2]) < float(source_points[f"{side}Shoulder"][2]), float(target_points[f"{side}Wrist"][2]) < float(target_points[f"{side}Shoulder"][2])),
                f"{side}WristBelowHead": (float(source_points[f"{side}Wrist"][2]) < float(source_points["head"][2]), float(target_points[f"{side}Wrist"][2]) < float(target_points["head"][2])),
                f"{side}AnkleBelowHip": (float(source_points[f"{side}Ankle"][2]) < float(source_points[f"{side}Hip"][2]), float(target_points[f"{side}Ankle"][2]) < float(target_points[f"{side}Hip"][2])),
            }
            for label, (source_value, target_value) in checks.items():
                frame_ordering[label] = {"source": source_value, "target": target_value}
                if source_value != target_value:
                    ordering_mismatches.append({"frame": index, "sourceFrame": int(frame["sourceFrame"]), "semantic": label, "source": source_value, "target": target_value})
            source_height = _normalized_wrist_height(source_points, side)
            target_height = _normalized_wrist_height(target_points, side)
            vertical_error = abs(source_height - target_height)
            if vertical_error > max_vertical[0]:
                max_vertical = (vertical_error, index, f"{side}WristVsPelvisHead")

        side_pairs = (("LeftUpperArm", "RightUpperArm"), ("LeftForeArm", "RightForeArm"), ("LeftThigh", "RightThigh"), ("LeftShin", "RightShin"))
        identity_details = []
        for left_name, right_name in side_pairs:
            source_left = source_direction_descriptor(frame["sourcePose"], retargeted["sourceRestWorld"], mapping, left_name)
            source_right = source_direction_descriptor(frame["sourcePose"], retargeted["sourceRestWorld"], mapping, right_name)
            target_left = target_direction_descriptor(frame["pose"], retargeted["targetRests"], mapping, left_name)
            target_right = target_direction_descriptor(frame["pose"], retargeted["targetRests"], mapping, right_name)
            same_error = max(_angle_degrees(source_left, target_left), _angle_degrees(source_right, target_right))
            cross_error = min(_angle_degrees(source_left, target_right), _angle_degrees(source_right, target_left))
            identity_details.append({"pair": f"{left_name}/{right_name}", "sameSideErrorDegrees": clean(same_error, 9), "crossSideErrorDegrees": clean(cross_error, 9)})
            if cross_error + 1e-6 < same_error:
                left_right_failures.append({"frame": index, "sourceFrame": int(frame["sourceFrame"]), "pair": f"{left_name}/{right_name}", "sameSideErrorDegrees": clean(same_error, 9), "crossSideErrorDegrees": clean(cross_error, 9)})
        target_side_order_ok = float(target_points["leftShoulder"][0]) < float(target_points["rightShoulder"][0]) and float(target_points["leftHip"][0]) < float(target_points["rightHip"][0])
        if not target_side_order_ok:
            left_right_failures.append({"frame": index, "sourceFrame": int(frame["sourceFrame"]), "pair": "target-side-order"})

        rows.append({"frame": index, "sourceFrame": int(frame["sourceFrame"]), "segmentDirectionErrorsDegrees": segment_errors, "bendErrors": bend_errors, "rootDirectionErrorDegrees": clean(root_error, 9), "ordering": frame_ordering, "leftRightIdentity": identity_details})

    max_arm = max_arm_direction[0]
    max_leg = max_leg_direction[0]
    max_elbow_value = max_elbow[0]
    max_knee_value = max_knee[0]
    max_root = max_root_direction[0]
    max_vertical_value = max_vertical[0]
    passed = (
        max_arm <= tolerance["directionDegrees"] and max_leg <= tolerance["directionDegrees"]
        and max_elbow_value <= tolerance["elbowBendDegrees"] and max_knee_value <= tolerance["kneeBendDegrees"]
        and max_root <= tolerance["rootDirectionDegrees"] and max_vertical_value <= tolerance["normalizedVerticalError"]
        and not ordering_mismatches and not left_right_failures
    )
    candidates = [
        (max_arm / tolerance["directionDegrees"], max_arm_direction[1], max_arm_direction[2], "armDirection", max_arm, tolerance["directionDegrees"]),
        (max_leg / tolerance["directionDegrees"], max_leg_direction[1], max_leg_direction[2], "legDirection", max_leg, tolerance["directionDegrees"]),
        (max_elbow_value / tolerance["elbowBendDegrees"], max_elbow[1], max_elbow[2], "elbowBend", max_elbow_value, tolerance["elbowBendDegrees"]),
        (max_knee_value / tolerance["kneeBendDegrees"], max_knee[1], max_knee[2], "kneeBend", max_knee_value, tolerance["kneeBendDegrees"]),
        (max_root / tolerance["rootDirectionDegrees"], max_root_direction[1], "root", "rootDirection", max_root, tolerance["rootDirectionDegrees"]),
        (max_vertical_value / tolerance["normalizedVerticalError"], max_vertical[1], max_vertical[2], "normalizedVertical", max_vertical_value, tolerance["normalizedVerticalError"]),
    ]
    worst = max(candidates, key=lambda row: row[0])
    return {
        "pass": bool(passed), "tolerance": dict(tolerance),
        "maxArmDirectionErrorDegrees": clean(max_arm, 9), "maxLegDirectionErrorDegrees": clean(max_leg, 9),
        "maxElbowBendErrorDegrees": clean(max_elbow_value, 9), "maxKneeBendErrorDegrees": clean(max_knee_value, 9),
        "maxRootDirectionErrorDegrees": clean(max_root, 9), "maxNormalizedVerticalError": clean(max_vertical_value, 9),
        "orderingMismatchCount": len(ordering_mismatches), "leftRightIdentityPass": not left_right_failures,
        "worst": {"frame": worst[1], "semantic": worst[2], "metric": worst[3], "value": clean(worst[4], 9), "tolerance": clean(worst[5], 9), "toleranceRatio": clean(worst[0], 9)},
        "perSegment": per_segment, "perJoint": per_joint, "orderingMismatches": ordering_mismatches,
        "leftRightFailures": left_right_failures, "frames": rows,
    }


def conversion_fidelity(retargeted: dict, normalized: dict, tolerance: float) -> dict:
    if len(retargeted["frames"]) != len(normalized["diagnostics"]):
        raise ValueError("retarget/normalization diagnostics frame count mismatch")
    per_semantic = {name: {"maxErrorMeters": 0.0, "worstFrame": None} for name in ACCEPTANCE_SEMANTICS}
    max_error, worst_frame, worst_semantic, rows = -1.0, None, None, []
    for index, (target, generated) in enumerate(zip(retargeted["frames"], normalized["diagnostics"]), start=1):
        desired, actual, errors = target["semantics"], generated["normalizedSemantics"], {}
        for semantic in ACCEPTANCE_SEMANTICS:
            if semantic not in desired or semantic not in actual:
                raise ValueError(f"missing fidelity semantic {semantic!r} at frame {index}")
            error = _distance(desired[semantic], tuple(actual[semantic]))
            errors[semantic] = clean(error, 9)
            if error > per_semantic[semantic]["maxErrorMeters"]:
                per_semantic[semantic] = {"maxErrorMeters": clean(error, 9), "worstFrame": index}
            if error > max_error:
                max_error, worst_frame, worst_semantic = error, index, semantic
        rows.append({"frame": index, "sourceFrame": int(target["sourceFrame"]), "errorsMeters": errors})
    max_error = max(0.0, max_error)
    return {"toleranceMeters": clean(tolerance, 9), "pass": bool(max_error <= tolerance), "maxErrorMeters": clean(max_error, 9), "worstFrame": worst_frame, "worstSemantic": worst_semantic, "perSemantic": per_semantic, "frames": rows}


def target_pose_rows(retargeted: dict) -> list[dict]:
    return [{"frame": index, "sourceFrame": int(frame["sourceFrame"]), "semantics": {key: clean_vec(value) for key, value in sorted(frame["semantics"].items()) if key in VISUAL_SEMANTICS}} for index, frame in enumerate(retargeted["frames"], start=1)]


def source_pose_rows(retargeted: dict) -> list[dict]:
    return [{"frame": index, "sourceFrame": int(frame["sourceFrame"]), "semantics": {key: clean_vec(value) for key, value in sorted(frame["sourceSemantics"].items()) if key in VISUAL_SEMANTICS}} for index, frame in enumerate(retargeted["frames"], start=1)]


def representation_limitations(mapping: dict, target_rig: dict, normalized: dict) -> list[dict]:
    directly_parameterized = {"Pelvis", "Spine", "Chest", "Head", "LeftClavicle", "RightClavicle", "LeftUpperArm", "LeftForeArm", "RightUpperArm", "RightForeArm", "LeftThigh", "LeftShin", "RightThigh", "RightShin"}
    omitted = sorted(set(mapping["targetToSource"]) - directly_parameterized)
    max_dropped, worst = 0.0, None
    for frame_index, frame in enumerate(normalized["diagnostics"], start=1):
        for row in frame["projection"]:
            for axis, value in row["droppedEulerDeg"].items():
                magnitude = abs(float(value))
                if magnitude > max_dropped:
                    max_dropped = magnitude
                    worst = {"frame": frame_index, "bone": row["bone"], "axis": axis, "degrees": clean(float(value), 9)}
    result = [{"type": "reduced-motion-contract", "detail": "Contract B stores full per-bone transforms while Contract A stores only the target rig motionContract semantics. Conversion is therefore explicitly lossy."}]
    if omitted:
        result.append({"type": "mapped-bones-without-direct-motion-channel", "targetBones": omitted, "detail": "These explicit mappings participate in retarget pose evaluation/diagnostics, but current Contract A has no independent channel for their full orientation."})
    result.append({"type": "projected-body-euler-components", "maxDroppedEulerDegrees": clean(max_dropped, 9), "worst": worst, "detail": "Body normalization projects target pose rotations onto axes declared by GameHumanoidV2.solvers.torso; omitted Euler components are reported, not hidden."})
    return result
