from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

from motion2sheet.motion.humanoid_motion.runner import select_even_samples
from motion2sheet.motion.humanoid_motion.schema import ROTATION_JOINTS, read_animation


ROOT = Path(__file__).parents[3]
SAMPLE = ROOT / "samples" / "humanoid_motion" / "animations" / "heavy-right-cross"
ANIMATION = SAMPLE / "animation.json"
GENERATOR = SAMPLE / "generate.py"

READY, COIL, LAUNCH, ACCELERATION, IMPACT, FOLLOW, RECOIL, RECOVER, SETTLE = 0, 2, 3, 4, 5, 6, 7, 8, 9


def _angle_degrees(first, second):
    dot = abs(sum(a * b for a, b in zip(first, second)))
    return math.degrees(2.0 * math.acos(max(-1.0, min(1.0, dot))))


def _track(animation, semantic):
    if semantic == "Hips":
        return animation["hips"]["rotations"]
    return animation["joints"][semantic]["rotations"]


def _excursion(animation, semantic):
    values = _track(animation, semantic)
    return max(_angle_degrees(values[READY], sample) for sample in values)


def _rotate_vector(quaternion, vector):
    w, x, y, z = quaternion
    vx, vy, vz = vector
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (
        vx + w * tx + (y * tz - z * ty),
        vy + w * ty + (z * tx - x * tz),
        vz + w * tz + (x * ty - y * tx),
    )


def _right_arm_direction(animation, semantic, frame):
    return _rotate_vector(_track(animation, semantic)[frame], (-1.0, 0.0, 0.0))


def _forward_alignment(animation, semantic, frame):
    return -_right_arm_direction(animation, semantic, frame)[1]


def _vector_angle_degrees(first, second):
    dot = sum(a * b for a, b in zip(first, second))
    length = math.sqrt(sum(v * v for v in first) * sum(v * v for v in second))
    return math.degrees(math.acos(max(-1.0, min(1.0, dot / length))))


def _pose_distance(animation, a, b, semantics):
    return sum(_angle_degrees(_track(animation, semantic)[a], _track(animation, semantic)[b]) for semantic in semantics)


def test_heavy_right_cross_contract_is_schema_valid_character_independent_and_in_place():
    animation = read_animation(ANIMATION)
    assert animation["id"] == "heavy-right-cross"
    assert animation["canonicalSkeleton"] == "humanoid_v1"
    assert animation["frameCount"] == 10
    assert animation["fps"] == 8.0
    assert animation["durationSeconds"] == 1.125
    assert animation["durationSeconds"] == (animation["frameCount"] - 1) / animation["fps"]
    assert animation["loop"] is False
    assert set(animation["joints"]) == set(ROTATION_JOINTS)
    assert all(sample == [0.0, 0.0, 0.0] for sample in animation["root"]["translations"])

    text = ANIMATION.read_text(encoding="utf-8").lower()
    for forbidden in ("warrok", "maria", "character-a", ".fbx", ".glb", "mixamorig", "modelpath", "targetbone"):
        assert forbidden not in text


def test_heavy_right_cross_has_bounded_body_led_mechanics_and_staged_recovery():
    animation = read_animation(ANIMATION)
    assert select_even_samples(animation["frameCount"], 10) == list(range(10))

    metrics = {semantic: _excursion(animation, semantic) for semantic in (
        "RightUpperArm", "RightLowerArm", "RightHand", "LeftUpperArm", "LeftLowerArm",
        "Hips", "Spine", "Chest", "RightUpperLeg", "RightFoot",
    )}

    assert 65.0 <= metrics["RightUpperArm"] <= 100.0
    assert 110.0 <= metrics["RightLowerArm"] <= 145.0
    assert 70.0 <= metrics["RightHand"] <= 135.0
    assert metrics["LeftUpperArm"] <= 12.0
    assert metrics["LeftLowerArm"] <= 12.0
    assert metrics["RightUpperArm"] >= metrics["LeftUpperArm"] + 55.0
    assert metrics["RightLowerArm"] >= metrics["LeftLowerArm"] + 100.0

    assert 30.0 <= metrics["Hips"] <= 50.0
    assert 12.0 <= metrics["Spine"] <= 28.0
    assert 18.0 <= metrics["Chest"] <= 35.0
    assert metrics["Hips"] >= metrics["Chest"] + 8.0
    assert metrics["Chest"] >= metrics["Spine"] + 3.0
    assert 20.0 <= metrics["RightUpperLeg"] <= 45.0
    assert 25.0 <= metrics["RightFoot"] <= 55.0

    hips_launch = _angle_degrees(_track(animation, "Hips")[COIL], _track(animation, "Hips")[LAUNCH])
    upper_launch = _angle_degrees(_track(animation, "RightUpperArm")[COIL], _track(animation, "RightUpperArm")[LAUNCH])
    assert 15.0 <= hips_launch <= 35.0
    assert hips_launch >= upper_launch + 4.0
    assert _forward_alignment(animation, "RightUpperArm", LAUNCH) >= 0.25
    assert _forward_alignment(animation, "RightLowerArm", LAUNCH) < 0.20

    assert _forward_alignment(animation, "RightUpperArm", ACCELERATION) >= 0.75
    assert _forward_alignment(animation, "RightLowerArm", ACCELERATION) >= 0.60

    for semantic in ("RightUpperArm", "RightLowerArm"):
        direction = _right_arm_direction(animation, semantic, IMPACT)
        assert -direction[1] >= 0.95
        assert abs(direction[0]) <= 0.20
        assert abs(direction[2]) <= 0.20

    impact_elbow_bend = _vector_angle_degrees(
        _right_arm_direction(animation, "RightUpperArm", IMPACT),
        _right_arm_direction(animation, "RightLowerArm", IMPACT),
    )
    assert 5.0 <= impact_elbow_bend <= 15.0
    assert _angle_degrees(_track(animation, "RightLowerArm")[IMPACT], _track(animation, "RightHand")[IMPACT]) <= 25.0

    impact_to_follow = _pose_distance(
        animation, IMPACT, FOLLOW,
        ("Hips", "Spine", "Chest", "RightShoulder", "RightUpperArm", "RightLowerArm", "RightHand", "RightFoot"),
    )
    follow_to_recoil = _pose_distance(
        animation, FOLLOW, RECOIL,
        ("Chest", "RightUpperArm", "RightLowerArm", "RightHand"),
    )
    assert impact_to_follow <= 35.0
    assert _forward_alignment(animation, "RightUpperArm", IMPACT) >= _forward_alignment(animation, "RightUpperArm", FOLLOW)
    assert _forward_alignment(animation, "RightLowerArm", IMPACT) >= _forward_alignment(animation, "RightLowerArm", FOLLOW)

    recoil_alignment = _forward_alignment(animation, "RightLowerArm", RECOIL)
    recover_alignment = _forward_alignment(animation, "RightLowerArm", RECOVER)
    assert 0.35 <= recoil_alignment <= 0.85
    assert recoil_alignment <= _forward_alignment(animation, "RightLowerArm", FOLLOW) - 0.20
    assert recover_alignment <= recoil_alignment - 0.20
    assert 60.0 <= follow_to_recoil <= 130.0

    hips_y = [sample[1] for sample in animation["hips"]["translations"]]
    coil_to_impact_forward_shift = hips_y[COIL] - hips_y[IMPACT]
    hips_shift = max(math.dist(animation["hips"]["translations"][READY], sample) for sample in animation["hips"]["translations"])
    assert 0.10 <= coil_to_impact_forward_shift <= 0.18
    assert 0.05 <= hips_shift <= 0.18

    ready_to_impact = _pose_distance(
        animation, READY, IMPACT,
        ("Hips", "Spine", "Chest", "RightShoulder", "RightUpperArm", "RightLowerArm", "RightHand", "RightFoot"),
    )
    impact_to_recoil = _pose_distance(
        animation, IMPACT, RECOIL,
        ("Hips", "Spine", "Chest", "RightUpperArm", "RightLowerArm", "RightHand"),
    )
    assert 300.0 <= ready_to_impact <= 520.0
    assert 80.0 <= impact_to_recoil <= 140.0
    assert _angle_degrees(_track(animation, "RightUpperArm")[READY], _track(animation, "RightUpperArm")[SETTLE]) <= 5.0


def test_heavy_right_cross_generator_is_byte_deterministic_and_matches_committed(tmp_path):
    outputs = [tmp_path / "a.json", tmp_path / "b.json"]
    for output in outputs:
        subprocess.run([sys.executable, str(GENERATOR), "--output", str(output)], cwd=ROOT, check=True)
    committed = ANIMATION.read_bytes()
    assert committed
    assert outputs[0].read_bytes() == outputs[1].read_bytes() == committed
