from __future__ import annotations

import copy

import pytest

from motion2sheet.motion.humanoid_motion.schema import (
    ANIMATION_SCHEMA,
    EXPECTED_COORDINATE_SYSTEM,
    EXPECTED_QUATERNION_CONVENTION,
    ROTATION_JOINTS,
)


def make_animation(animation_id: str = "candidate") -> dict:
    identity = [1.0, 0.0, 0.0, 0.0]
    return {
        "schema": ANIMATION_SCHEMA,
        "version": 1,
        "id": animation_id,
        "canonicalSkeleton": "humanoid_v1",
        "durationSeconds": 1.0 / 30.0,
        "fps": 30.0,
        "frameCount": 2,
        "loop": False,
        "coordinateSystem": copy.deepcopy(EXPECTED_COORDINATE_SYSTEM),
        "quaternionConvention": copy.deepcopy(EXPECTED_QUATERNION_CONVENTION),
        "root": {
            "translations": [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
            "rotations": [identity[:], identity[:]],
        },
        "hips": {
            "translations": [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
            "rotations": [identity[:], identity[:]],
        },
        "joints": {
            semantic: {"rotations": [identity[:], identity[:]]}
            for semantic in ROTATION_JOINTS
        },
    }


@pytest.fixture
def animation_document():
    return make_animation()
