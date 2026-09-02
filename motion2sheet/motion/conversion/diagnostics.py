from __future__ import annotations

from .math3d import clean, clean_vec, distance

ACCEPTANCE_SEMANTICS = (
    "root",
    "pelvis",
    "head",
    "leftElbow",
    "leftWrist",
    "rightElbow",
    "rightWrist",
    "leftKnee",
    "leftAnkle",
    "rightKnee",
    "rightAnkle",
)


def conversion_fidelity(retargeted: dict, normalized: dict, tolerance: float) -> dict:
    if len(retargeted["frames"]) != len(normalized["diagnostics"]):
        raise ValueError("retarget/normalization diagnostics frame count mismatch")
    per_semantic = {name: {"maxErrorMeters": 0.0, "worstFrame": None} for name in ACCEPTANCE_SEMANTICS}
    max_error = -1.0
    worst_frame = None
    worst_semantic = None
    rows = []
    for index, (target, generated) in enumerate(zip(retargeted["frames"], normalized["diagnostics"]), start=1):
        desired = target["semantics"]
        actual = generated["normalizedSemantics"]
        errors = {}
        for semantic in ACCEPTANCE_SEMANTICS:
            if semantic not in desired or semantic not in actual:
                raise ValueError(f"missing fidelity semantic {semantic!r} at frame {index}")
            error = distance(desired[semantic], tuple(actual[semantic]))
            errors[semantic] = clean(error, 9)
            if error > per_semantic[semantic]["maxErrorMeters"]:
                per_semantic[semantic] = {"maxErrorMeters": clean(error, 9), "worstFrame": index}
            if error > max_error:
                max_error = error
                worst_frame = index
                worst_semantic = semantic
        rows.append({"frame": index, "sourceFrame": int(target["sourceFrame"]), "errorsMeters": errors})
    max_error = max(0.0, max_error)
    return {
        "toleranceMeters": clean(tolerance, 9),
        "pass": bool(max_error <= tolerance),
        "maxErrorMeters": clean(max_error, 9),
        "worstFrame": worst_frame,
        "worstSemantic": worst_semantic,
        "perSemantic": per_semantic,
        "frames": rows,
    }


def target_pose_rows(retargeted: dict) -> list[dict]:
    rows = []
    for index, frame in enumerate(retargeted["frames"], start=1):
        rows.append({
            "frame": index,
            "sourceFrame": int(frame["sourceFrame"]),
            "semantics": {
                key: clean_vec(value)
                for key, value in sorted(frame["semantics"].items())
                if key in ACCEPTANCE_SEMANTICS
            },
        })
    return rows


def representation_limitations(mapping: dict, target_rig: dict, normalized: dict) -> list[dict]:
    directly_parameterized = {
        "Pelvis", "Spine", "Chest", "Head", "LeftClavicle", "RightClavicle",
        "LeftUpperArm", "LeftForeArm", "RightUpperArm", "RightForeArm",
        "LeftThigh", "LeftShin", "RightThigh", "RightShin",
    }
    omitted = sorted(set(mapping["targetToSource"]) - directly_parameterized)
    max_dropped = 0.0
    worst = None
    for frame_index, frame in enumerate(normalized["diagnostics"], start=1):
        for row in frame["projection"]:
            for axis, value in row["droppedEulerDeg"].items():
                magnitude = abs(float(value))
                if magnitude > max_dropped:
                    max_dropped = magnitude
                    worst = {"frame": frame_index, "bone": row["bone"], "axis": axis, "degrees": clean(float(value), 9)}
    result = [{
        "type": "reduced-motion-contract",
        "detail": "Contract B stores full per-bone transforms while Contract A stores only the target rig motionContract semantics. Conversion is therefore explicitly lossy.",
    }]
    if omitted:
        result.append({
            "type": "mapped-bones-without-direct-motion-channel",
            "targetBones": omitted,
            "detail": "These explicit mappings participate in retarget pose evaluation/diagnostics, but current Contract A has no independent channel for their full orientation.",
        })
    result.append({
        "type": "projected-body-euler-components",
        "maxDroppedEulerDegrees": clean(max_dropped, 9),
        "worst": worst,
        "detail": "Body normalization projects target pose rotations onto axes declared by GameHumanoidV2.solvers.torso; omitted Euler components are reported, not hidden.",
    })
    return result
