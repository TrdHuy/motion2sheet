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

READY, COIL, LAUNCH, ACCELERATION, IMPACT, FOLLOW, RECOIL, SETTLE = 0, 2, 3, 4, 5, 6, 7, 9


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
    # q * v * q^-1, expanded for a normalized wxyz quaternion.
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (
        vx + w * tx + (y * tz - z * ty),
        vy + w * ty + (z * tx - x * tz),
        vz + w * tz + (x * ty - y * tx),
    )


def _right_arm_direction(animation, semantic, frame):
    # humanoid_v1 canonical rest is a T-pose; physical Right arm points along -X.
    return _rotate_vector(_track(animation, semantic)[frame], (-1.0, 0.0, 0.0))


def _forward_alignment(animation, semantic, frame):
    # Canonical forward is -Y.
    return -_right_arm_direction(animation, semantic, frame)[1]


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


def test_heavy_right_cross_has_body_led_launch_direct_impact_and_recovery():
    animation = read_animation(ANIMATION)
    assert select_even_samples(animation["frameCount"], 10) == list(range(10))

    right_upper = _excursion(animation, "RightUpperArm")
    right_lower = _excursion(animation, "RightLowerArm")
    left_upper = _excursion(animation, "LeftUpperArm")
    left_lower = _excursion(animation, "LeftLowerArm")
    hips = _excursion(animation, "Hips")
    spine = _excursion(animation, "Spine")
    chest = _excursion(animation, "Chest")
    rear_leg = _excursion(animation, "RightUpperLeg")
    rear_foot = _excursion(animation, "RightFoot")

    assert right_upper >= 75.0
    assert right_lower >= 130.0
    assert left_upper <= 12.0
    assert left_lower <= 12.0
    assert right_upper >= left_upper + 60.0
    assert right_lower >= left_lower + 110.0
    assert hips >= 30.0
    assert spine >= 20.0
    assert chest >= 30.0
    assert rear_leg >= 20.0
    assert rear_foot >= 25.0

    # F2 -> F3: Hips reverse first while the right arm only begins leaving guard.
    hips_launch = _angle_degrees(_track(animation, "Hips")[COIL], _track(animation, "Hips")[LAUNCH])
    upper_launch = _angle_degrees(
        _track(animation, "RightUpperArm")[COIL],
        _track(animation, "RightUpperArm")[LAUNCH],
    )
    assert hips_launch >= 15.0
    assert hips_launch >= upper_launch + 2.0
    assert _forward_alignment(animation, "RightUpperArm", LAUNCH) >= 0.25
    assert _forward_alignment(animation, "RightLowerArm", LAUNCH) < 0.20

    # F4 acceleration and locked F5 hero impact progressively align both arm
    # segments with the canonical forward axis instead of sweeping sideways.
    assert _forward_alignment(animation, "RightUpperArm", ACCELERATION) >= 0.75
    assert _forward_alignment(animation, "RightLowerArm", ACCELERATION) >= 0.60
    for semantic in ("RightUpperArm", "RightLowerArm"):
        direction = _right_arm_direction(animation, semantic, IMPACT)
        assert -direction[1] >= 0.95
        assert abs(direction[0]) <= 0.20
        assert abs(direction[2]) <= 0.20

    # F6 remains committed through target; F7 is a genuine recoil.
    assert _forward_alignment(animation, "RightUpperArm", FOLLOW) >= 0.95
    assert _forward_alignment(animation, "RightLowerArm", FOLLOW) >= 0.95
    assert _forward_alignment(animation, "RightLowerArm", RECOIL) < 0.20

    hips_y = [sample[1] for sample in animation["hips"]["translations"]]
    assert hips_y[COIL] > hips_y[READY]
    assert hips_y[IMPACT] < hips_y[READY]
    assert hips_y[COIL] - hips_y[IMPACT] >= 0.075

    impact_to_recoil = sum(
        _angle_degrees(_track(animation, semantic)[IMPACT], _track(animation, semantic)[RECOIL])
        for semantic in ("Hips", "Spine", "Chest", "RightUpperArm", "RightLowerArm", "RightHand")
    )
    assert impact_to_recoil >= 150.0
    assert _angle_degrees(_track(animation, "RightUpperArm")[READY], _track(animation, "RightUpperArm")[SETTLE]) <= 5.0


def test_heavy_right_cross_generator_is_byte_deterministic_and_matches_committed(tmp_path):
    outputs = [tmp_path / "a.json", tmp_path / "b.json"]
    for output in outputs:
        subprocess.run([sys.executable, str(GENERATOR), "--output", str(output)], cwd=ROOT, check=True)
    committed = ANIMATION.read_bytes()
    assert committed
    assert outputs[0].read_bytes() == outputs[1].read_bytes() == committed
