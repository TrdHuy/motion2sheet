from __future__ import annotations

import copy

from motion2sheet.motion.conversion.diagnostics import source_retarget_fidelity
from motion2sheet.motion.conversion.math3d import distance, rest_matrix, rotation4, with_rotation
from motion2sheet.motion.conversion.retarget import BoneRest, _transfer_rotation


def _y(rotation):
    return rotation[0][1], rotation[1][1], rotation[2][1]


def test_per_bone_anatomical_basis_keeps_downward_arm_down():
    source_rest = rotation4(rest_matrix([0, 0, 0], [1, 0, 0], 1.53))
    source_pose = rotation4(rest_matrix([0, 0, 0], [0.20, 0.05, -0.98], 1.10))
    target_rest = rotation4(rest_matrix([0, 0, 0], [-0.30, 0, -0.11], 0.0))
    result = _transfer_rotation(source_pose_rotation=source_pose, source_rest_rotation=source_rest, target_rest_rotation=target_rest, source_reference_axis="+Z", target_reference_axis="+Z", source_to_target_axes=((1.0,0.0,0.0),(0.0,1.0,0.0),(0.0,0.0,1.0)), label="unit left arm")
    assert _y(result)[2] < -0.60


def _fake_retargeted():
    target_geometry = {
        "LeftUpperArm": ([-0.2,0,1.5],[-0.5,0,1.4]), "LeftForeArm": ([-0.5,0,1.4],[-0.75,0,1.2]),
        "RightUpperArm": ([0.2,0,1.5],[0.5,0,1.4]), "RightForeArm": ([0.5,0,1.4],[0.75,0,1.2]),
        "LeftThigh": ([-0.15,0,1.0],[-0.2,0,0.55]), "LeftShin": ([-0.2,0,0.55],[-0.25,0,0.1]),
        "RightThigh": ([0.15,0,1.0],[0.2,0,0.55]), "RightShin": ([0.2,0,0.55],[0.25,0,0.1]),
    }
    target_rests, source_rests, source_pose, target_pose = {}, {}, {}, {}
    target_to_source, source_refs, target_refs = {}, {}, {}
    for target, (head, tail) in target_geometry.items():
        matrix = rest_matrix(head, tail, 0.0)
        target_rests[target] = BoneRest(target, None, matrix, distance(tuple(head), tuple(tail)))
        source = f"src:{target}"
        source_rests[source] = matrix; source_pose[source] = matrix; target_pose[target] = matrix
        target_to_source[target] = source
        ref = "+Z" if "Arm" in target or "ForeArm" in target else "-Y"
        source_refs[target] = ref; target_refs[target] = ref
    points = {
        "pelvis": (0.0,0.0,1.0), "head": (0.0,0.0,2.0),
        "leftShoulder": (-0.2,0.0,1.5), "leftElbow": (-0.5,0.0,1.4), "leftWrist": (-0.75,0.0,1.2),
        "rightShoulder": (0.2,0.0,1.5), "rightElbow": (0.5,0.0,1.4), "rightWrist": (0.75,0.0,1.2),
        "leftHip": (-0.15,0.0,1.0), "leftKnee": (-0.2,0.0,0.55), "leftAnkle": (-0.25,0.0,0.1),
        "rightHip": (0.15,0.0,1.0), "rightKnee": (0.2,0.0,0.55), "rightAnkle": (0.25,0.0,0.1),
    }
    mapping = {"targetToSource": target_to_source, "targetToSourceReferenceAxis": source_refs, "targetToTargetReferenceAxis": target_refs, "sourceToTargetAxes": ((1.0,0.0,0.0),(0.0,1.0,0.0),(0.0,0.0,1.0)), "semanticRetargetTolerance": {"directionDegrees":0.05,"elbowBendDegrees":12.0,"kneeBendDegrees":1.1,"rootDirectionDegrees":0.05,"normalizedVerticalError":0.30}}
    retargeted = {"sourceRestWorld": source_rests, "targetRests": target_rests, "frames": [{"sourceFrame":1,"sourceRootDelta":(0.0,0.0,0.0),"rootTranslation":(0.0,0.0,0.0),"sourcePose":source_pose,"sourceSemantics":copy.deepcopy(points),"pose":target_pose,"semantics":copy.deepcopy(points)}]}
    return retargeted, mapping


def test_source_to_retarget_semantic_gate_rejects_arm_direction_corruption():
    retargeted, mapping = _fake_retargeted()
    assert source_retarget_fidelity(retargeted, mapping)["pass"] is True
    corrupted = copy.deepcopy(retargeted)
    upward = rotation4(rest_matrix([0,0,0],[0,0,1],0.0))
    corrupted["frames"][0]["pose"]["LeftUpperArm"] = with_rotation(corrupted["frames"][0]["pose"]["LeftUpperArm"], upward)
    report = source_retarget_fidelity(corrupted, mapping)
    assert report["pass"] is False
    assert report["maxArmDirectionErrorDegrees"] > report["tolerance"]["directionDegrees"]
