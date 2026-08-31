from pathlib import Path

import pytest

from motion2sheet.anim2sheet.common.profile import (
    load_animation_profile,
    load_joint_contract,
    load_rig_profile,
    resolve_execution_frames,
)

PROFILE_PATH = Path("profiles/anim2sheet/animations/gale_slash/animation.json5")
RIG_PATH = Path("profiles/anim2sheet/rigs/game_humanoid_v2.json5")
CONTRACT_PATH = Path("profiles/anim2sheet/animations/gale_slash/joint_contract.json")


def contract():
    profile = load_animation_profile(PROFILE_PATH)
    rig = load_rig_profile(RIG_PATH)
    return load_joint_contract(CONTRACT_PATH, frame_count=int(profile["frames"]), rig_profile=rig)


def test_canonical_contract_is_full_f1_f16():
    value = contract()
    assert value["reviewFrames"] == list(range(1, 17))
    assert resolve_execution_frames(value, None) == list(range(1, 17))


def test_execution_subset_does_not_mutate_contract():
    value = contract()
    assert resolve_execution_frames(value, "7,8") == [7, 8]
    assert value["reviewFrames"] == list(range(1, 17))


def test_frame_outside_contract_fails_fast():
    with pytest.raises(ValueError, match="outside contract"):
        resolve_execution_frames(contract(), "17")
