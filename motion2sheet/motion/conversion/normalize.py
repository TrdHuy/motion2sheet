from __future__ import annotations

import math

from .math3d import (
    Mat3,
    Mat4,
    Vec3,
    add,
    clean,
    clean_vec,
    euler_xyz_from_matrix,
    euler_xyz_matrix,
    from_rotation_translation,
    inverse_affine,
    length,
    mul,
    mul3,
    mul4,
    rotation4,
    sub,
    transpose3,
    translation4,
    unit,
)
from .retarget import BoneRest


def _axis_index(axis: str) -> int:
    try:
        return {"X": 0, "Y": 1, "Z": 2}[axis.upper()]
    except KeyError as exc:
        raise ValueError(f"unsupported target solver axis {axis!r}") from exc


def _project_torso(required_basis: Mat3, row: dict, solver: dict) -> tuple[Mat3, dict[str, float], dict]:
    euler = euler_xyz_from_matrix(required_basis)
    yaw_axis = str(solver["yawAxis"]).upper()
    lean_axis = str(solver["leanAxis"]).upper()
    lean_sign = float(solver["leanSign"])
    yaw_value = euler[_axis_index(yaw_axis)]
    lean_axis_value = euler[_axis_index(lean_axis)]
    fields = {
        str(row["yawField"]): clean(math.degrees(yaw_value), 9),
        str(row["leanField"]): clean(math.degrees(lean_axis_value) / lean_sign, 9),
    }
    projected = [0.0, 0.0, 0.0]
    projected[_axis_index(yaw_axis)] = yaw_value
    projected[_axis_index(lean_axis)] = lean_axis_value
    dropped = {
        axis: clean(math.degrees(euler[index] - projected[index]), 9)
        for index, axis in enumerate(("X", "Y", "Z"))
        if abs(euler[index] - projected[index]) > 1e-10
    }
    return euler_xyz_matrix(*projected), fields, {"bone": str(row["bone"]), "droppedEulerDeg": dropped}


def _project_clavicle(required_basis: Mat3, row: dict) -> tuple[Mat3, dict[str, float], dict]:
    euler = euler_xyz_from_matrix(required_basis)
    axis = str(row.get("axis", "Z")).upper()
    sign = float(row.get("sign", 1.0))
    axis_index = _axis_index(axis)
    angle = euler[axis_index]
    field = str(row["field"])
    fields = {field: clean(math.degrees(angle) / sign, 9)}
    projected = [0.0, 0.0, 0.0]
    projected[axis_index] = angle
    dropped = {
        candidate: clean(math.degrees(euler[index] - projected[index]), 9)
        for index, candidate in enumerate(("X", "Y", "Z"))
        if abs(euler[index] - projected[index]) > 1e-10
    }
    return euler_xyz_matrix(*projected), fields, {"bone": str(row["bone"]), "droppedEulerDeg": dropped}


def _rest_local(rests: dict[str, BoneRest], name: str) -> Mat4:
    rest = rests[name]
    if rest.parent is None:
        return rest.matrix
    return mul4(inverse_affine(rests[rest.parent].matrix), rest.matrix)


def _pose_with_rotation(base: Mat4, rotation: Mat3) -> Mat4:
    return from_rotation_translation(rotation, translation4(base))


def _normalized_body_pose(desired_pose: dict[str, Mat4], rests: dict[str, BoneRest], order: list[str], target_rig: dict) -> tuple[dict[str, Mat4], dict[str, float], list[dict]]:
    torso = target_rig["solvers"]["torso"]
    body_rows = {str(row["bone"]): row for row in torso["bodyChannels"]}
    clavicle_rows = {str(row["bone"]): row for row in torso["clavicleChannels"]}
    normalized: dict[str, Mat4] = {}
    fields: dict[str, float] = {}
    projection: list[dict] = []
    for name in order:
        rest = rests[name]
        if rest.parent is None:
            base = rest.matrix
        else:
            base = mul4(normalized[rest.parent], _rest_local(rests, name))
        desired_rotation = rotation4(desired_pose[name])
        required_basis = mul3(transpose3(rotation4(base)), desired_rotation)
        if name in body_rows:
            basis, values, row_diag = _project_torso(required_basis, body_rows[name], torso)
            fields.update(values)
            projection.append(row_diag)
            normalized[name] = _pose_with_rotation(base, mul3(rotation4(base), basis))
        elif name in clavicle_rows:
            basis, values, row_diag = _project_clavicle(required_basis, clavicle_rows[name])
            fields.update(values)
            projection.append(row_diag)
            normalized[name] = _pose_with_rotation(base, mul3(rotation4(base), basis))
        else:
            normalized[name] = base
    expected = {
        str(row["semantic"])
        for row in target_rig["motionContract"]["bodyChannels"]
        if bool(row.get("required", True))
    }
    if set(fields) != expected:
        raise ValueError(
            f"normalization body channel mismatch: missing={sorted(expected-set(fields))} extra={sorted(set(fields)-expected)}"
        )
    return normalized, fields, projection


def _head(matrix: Mat4) -> Vec3:
    return translation4(matrix)


def _tail(matrix: Mat4, bone_length: float) -> Vec3:
    r = rotation4(matrix)
    return add(translation4(matrix), mul((r[0][1], r[1][1], r[2][1]), bone_length))


def _base_for_bone(normalized: dict[str, Mat4], rests: dict[str, BoneRest], name: str) -> Mat4:
    rest = rests[name]
    if rest.parent is None:
        return rest.matrix
    return mul4(normalized[rest.parent], _rest_local(rests, name))


def _reanchor_segment(start: Vec3, desired_start: Vec3, desired_end: Vec3, target_length: float, label: str) -> Vec3:
    direction = unit(sub(desired_end, desired_start), label)
    return add(start, mul(direction, target_length))


def _knee_guide(hip: Vec3, knee: Vec3, ankle: Vec3, *, guide_distance: float, fallback_bend: Vec3) -> tuple[Vec3, bool]:
    axis = sub(ankle, hip)
    axis_length_sq = sum(value * value for value in axis)
    if axis_length_sq <= 1e-10:
        raise ValueError("hip and ankle are coincident while deriving knee guide")
    t = sum((knee[i] - hip[i]) * axis[i] for i in range(3)) / axis_length_sq
    projection = add(hip, mul(axis, t))
    bend = sub(knee, projection)
    fallback = False
    if length(bend) <= 1e-6:
        bend = fallback_bend
        fallback = True
    # Contract A kneeGuide is authored world-space bend-plane authority.  The
    # target rig's poleAngleDeg calibrates the IK constraint to the mirrored
    # rest bases; it is not an instruction to rotate the authored guide.
    # Existing leg_ik diagnostics explicitly require evaluated knee bend and
    # guide bend to point to the same half-plane for both left and right legs.
    guide_dir = unit(bend, "knee bend plane")
    return add(projection, mul(guide_dir, guide_distance)), fallback


def _contract_specs(target_rig: dict, key: str) -> set[str]:
    return {
        str(row["semantic"])
        for row in target_rig["motionContract"][key]
        if bool(row.get("required", True))
    }


def normalize_frame(retarget_frame: dict, target_rig: dict, rests: dict[str, BoneRest], order: list[str], *, output_frame: int) -> tuple[dict, dict]:
    desired_pose = retarget_frame["pose"]
    root_translation: Vec3 = retarget_frame["rootTranslation"]
    normalized, body, projection_diag = _normalized_body_pose(desired_pose, rests, order, target_rig)

    joints: dict[str, list[float]] = {}
    normalized_points: dict[str, Vec3] = {
        "root": root_translation,
        "pelvis": add(_head(normalized["Pelvis"]), root_translation),
        "head": add(_tail(normalized["Head"], rests["Head"].length), root_translation),
    }

    arm_sides = target_rig["solvers"]["arms"]["sides"]
    for side in ("left", "right"):
        cfg = arm_sides[side]
        upper = str(cfg["upperBone"])
        fore = str(cfg["foreBone"])
        desired = retarget_frame["semantics"]
        shoulder_key = f"{side}Shoulder"
        elbow_key = str(cfg["elbowJoint"])
        wrist_key = str(cfg["wristJoint"])
        shoulder = add(_head(_base_for_bone(normalized, rests, upper)), root_translation)
        elbow = _reanchor_segment(shoulder, desired[shoulder_key], desired[elbow_key], rests[upper].length, f"{side} upper-arm direction")
        wrist = _reanchor_segment(elbow, desired[elbow_key], desired[wrist_key], rests[fore].length, f"{side} forearm direction")
        joints[elbow_key] = clean_vec(elbow)
        joints[wrist_key] = clean_vec(wrist)
        normalized_points[elbow_key] = elbow
        normalized_points[wrist_key] = wrist

    targets: dict[str, list[float]] = {}
    leg_sides = target_rig["solvers"]["legs"]["sides"]
    knee_fallbacks: list[str] = []
    for side in ("left", "right"):
        cfg = leg_sides[side]
        thigh = str(cfg["thighBone"])
        shin = str(cfg["shinBone"])
        desired = retarget_frame["semantics"]
        hip_key, knee_key = f"{side}Hip", f"{side}Knee"
        ankle_key = str(cfg["ankleTarget"])
        guide_key = str(cfg["kneeGuideTarget"])
        hip = add(_head(_base_for_bone(normalized, rests, thigh)), root_translation)
        knee = _reanchor_segment(hip, desired[hip_key], desired[knee_key], rests[thigh].length, f"{side} thigh direction")
        ankle = _reanchor_segment(knee, desired[knee_key], desired[ankle_key], rests[shin].length, f"{side} shin direction")
        rest_hip = _head(rests[thigh].matrix)
        rest_knee = _tail(rests[thigh].matrix, rests[thigh].length)
        rest_ankle = _tail(rests[shin].matrix, rests[shin].length)
        rest_axis = sub(rest_ankle, rest_hip)
        rest_t = sum((rest_knee[i] - rest_hip[i]) * rest_axis[i] for i in range(3)) / sum(value * value for value in rest_axis)
        rest_projection = add(rest_hip, mul(rest_axis, rest_t))
        fallback_bend = sub(rest_knee, rest_projection)
        guide, fallback = _knee_guide(
            hip,
            knee,
            ankle,
            guide_distance=max(0.45, (rests[thigh].length + rests[shin].length) * 0.65),
            fallback_bend=fallback_bend,
        )
        if fallback:
            knee_fallbacks.append(side)
        targets[ankle_key] = clean_vec(ankle)
        targets[guide_key] = clean_vec(guide)
        normalized_points[knee_key] = knee
        normalized_points[ankle_key] = ankle

    if set(joints) != _contract_specs(target_rig, "jointChannels"):
        raise ValueError(f"normalization joint channels do not match target motionContract: {sorted(joints)}")
    if set(targets) != _contract_specs(target_rig, "targetChannels"):
        raise ValueError(f"normalization target channels do not match target motionContract: {sorted(targets)}")

    frame = {
        "frame": int(output_frame),
        "root": {"translation": clean_vec(root_translation)},
        "body": {key: clean(value) for key, value in sorted(body.items())},
        "joints": {key: joints[key] for key in sorted(joints)},
        "targets": {key: targets[key] for key in sorted(targets)},
    }
    diagnostic = {
        "sourceFrame": int(retarget_frame["sourceFrame"]),
        "projection": projection_diag,
        "kneeGuideFallbackSides": knee_fallbacks,
        "normalizedSemantics": {key: clean_vec(value) for key, value in sorted(normalized_points.items())},
    }
    return frame, diagnostic


def normalize_animation(retargeted: dict, target_rig: dict) -> dict:
    frames = []
    diagnostics = []
    for index, retarget_frame in enumerate(retargeted["frames"], start=1):
        frame, diagnostic = normalize_frame(
            retarget_frame,
            target_rig,
            retargeted["targetRests"],
            retargeted["targetOrder"],
            output_frame=index,
        )
        frames.append(frame)
        diagnostics.append(diagnostic)
    return {"frames": frames, "diagnostics": diagnostics}
