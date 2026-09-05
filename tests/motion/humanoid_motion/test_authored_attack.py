from __future__ import annotations

import hashlib
import math
import subprocess
import sys
from pathlib import Path

from motion2sheet.motion.humanoid_motion.runner import select_even_samples
from motion2sheet.motion.humanoid_motion.schema import ROTATION_JOINTS, read_animation


ROOT = Path(__file__).parents[3]
SAMPLE = ROOT / "samples" / "humanoid_motion" / "animations" / "right-overhand-smash"
ANIMATION = SAMPLE / "animation.json"
GENERATOR = SAMPLE / "generate.py"


def _angle_degrees(first, second):
    dot = abs(sum(a * b for a, b in zip(first, second)))
    return math.degrees(2.0 * math.acos(max(-1.0, min(1.0, dot))))


def _track(animation, semantic):
    if semantic == "Hips":
        return animation["hips"]["rotations"]
    return animation["joints"][semantic]["rotations"]


def _excursion(animation, semantic):
    values = _track(animation, semantic)
    return max(_angle_degrees(values[0], sample) for sample in values)


def test_direct_authored_attack_sample_is_schema_valid_character_independent_and_in_place():
    animation = read_animation(ANIMATION)
    assert animation["id"] == "right-overhand-smash"
    assert animation["canonicalSkeleton"] == "humanoid_v1"
    assert animation["frameCount"] == 8
    assert animation["fps"] == 8.0
    assert animation["durationSeconds"] == (animation["frameCount"] - 1) / animation["fps"]
    assert animation["loop"] is False
    assert set(animation["joints"]) == set(ROTATION_JOINTS)
    assert all(sample == [0.0, 0.0, 0.0] for sample in animation["root"]["translations"])

    text = ANIMATION.read_text(encoding="utf-8").lower()
    for forbidden in ("warrok", "maria", "character-a", ".fbx", ".glb", "mixamorig", "modelpath", "targetbone"):
        assert forbidden not in text


def test_direct_authored_attack_has_readable_right_side_motion_and_sparse_phase_coverage():
    animation = read_animation(ANIMATION)
    assert select_even_samples(animation["frameCount"], 8) == list(range(8))

    right_upper = _excursion(animation, "RightUpperArm")
    right_lower = _excursion(animation, "RightLowerArm")
    left_upper = _excursion(animation, "LeftUpperArm")
    left_lower = _excursion(animation, "LeftLowerArm")
    chest = _excursion(animation, "Chest")
    spine = _excursion(animation, "Spine")

    assert right_upper >= 80.0
    assert right_lower >= 120.0
    assert right_upper >= left_upper + 60.0
    assert right_lower >= left_lower + 90.0
    assert chest >= 25.0
    assert spine >= 18.0

    impact = 4
    recovery = 6
    impact_to_recovery = sum(
        _angle_degrees(_track(animation, semantic)[impact], _track(animation, semantic)[recovery])
        for semantic in ("Hips", "Spine", "Chest", "RightUpperArm", "RightLowerArm", "RightHand")
    )
    assert impact_to_recovery >= 160.0


def test_direct_authored_attack_generator_is_byte_deterministic_and_matches_committed(tmp_path):
    outputs = [tmp_path / "a.json", tmp_path / "b.json"]
    for output in outputs:
        subprocess.run([sys.executable, str(GENERATOR), "--output", str(output)], cwd=ROOT, check=True)
    committed = ANIMATION.read_bytes()
    assert outputs[0].read_bytes() == outputs[1].read_bytes() == committed
    assert hashlib.sha256(committed).hexdigest() == "25f79d315f71778a6d3bf39f2e45ced864392112fe3ff5d73371571e75e711f4"
