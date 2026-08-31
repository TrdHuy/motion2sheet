from pathlib import Path

import pytest

from motion2sheet.anim2sheet.animations.gale_slash.contract import (
    load_joint_contract,
    resolve_execution_frames,
)


CONTRACT = Path("profiles/anim2sheet/animations/gale_slash/joint_contract.json")


def test_canonical_contract_is_full_f1_f16():
    contract = load_joint_contract(CONTRACT)
    assert contract["reviewFrames"] == list(range(1, 17))
    assert resolve_execution_frames(contract, None) == list(range(1, 17))


def test_execution_subset_does_not_mutate_contract():
    contract = load_joint_contract(CONTRACT)
    assert resolve_execution_frames(contract, "7,8") == [7, 8]
    assert contract["reviewFrames"] == list(range(1, 17))


def test_frame_outside_contract_fails_fast():
    contract = load_joint_contract(CONTRACT)
    with pytest.raises(ValueError, match="outside contract"):
        resolve_execution_frames(contract, "17")
