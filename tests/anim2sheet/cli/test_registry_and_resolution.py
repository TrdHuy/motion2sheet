from __future__ import annotations

from pathlib import Path

import pytest

from motion2sheet.anim2sheet.cli import parser as cli_parser
from motion2sheet.anim2sheet.common.profile import resolve_review_request
from motion2sheet.anim2sheet.registry import get_authoring_capability

ROOT = Path(__file__).resolve().parents[3]
GALE = ROOT / "profiles/anim2sheet/animations/gale_slash/animation.json5"
IDLE = ROOT / "profiles/anim2sheet/animations/sword_idle/animation.json5"
CAMERAS = ROOT / "profiles/anim2sheet/cameras/fast_keypose_review.json"


def resolve(profile: Path, *, frames=None, cameras=None, animation=None):
    return resolve_review_request(
        profile_path=profile,
        camera_profile_path=CAMERAS,
        frames=frames,
        cameras=cameras,
        animation=animation,
    )


def execution_argv(command: str, profile: Path = GALE) -> list[str]:
    return [
        command,
        "--profile", str(profile),
        "--camera-profile", str(CAMERAS),
        "--output", "build/test",
    ]


def test_registry_resolves_authoring_capability_not_clip():
    definition = get_authoring_capability("humanoid_v2")
    assert definition.capability == "humanoid_v2"
    assert definition.blender_author == "common/authoring/humanoid.py"


def test_unknown_authoring_capability_fails():
    with pytest.raises(ValueError, match="Unsupported anim2sheet authoring capability"):
        get_authoring_capability("missing")


def test_gale_and_idle_resolve_same_generic_authoring_stack():
    gale = resolve(GALE)
    idle = resolve(IDLE)
    assert gale["animation"] == "gale_slash"
    assert idle["animation"] == "sword_idle"
    assert gale["authoringCapability"] == idle["authoringCapability"] == "humanoid_v2"
    assert gale["rigProfilePath"] == idle["rigProfilePath"]
    assert gale["characterProfilePath"] == idle["characterProfilePath"]
    assert gale["source"]["generator"] == idle["source"]["generator"] == "profile-driven-humanoid-v1"


def test_gale_review_without_frames_uses_profile_contract_frames():
    request = resolve(GALE)
    assert request["executionFrames"] == list(range(1, 17))
    assert request["contractFrames"] == list(range(1, 17))


def test_idle_review_uses_its_own_data_frame_count():
    request = resolve(IDLE)
    assert request["executionFrames"] == [1, 2, 3, 4]
    assert request["contractFrames"] == [1, 2, 3, 4]


def test_review_frame_subset_is_generic():
    assert resolve(GALE, frames="7,8")["executionFrames"] == [7, 8]
    assert resolve(IDLE, frames="2,3")["executionFrames"] == [2, 3]


def test_review_frame_outside_contract_fails_fast():
    with pytest.raises(ValueError, match="outside contract"):
        resolve(IDLE, frames="5")


def test_animation_flag_is_only_a_profile_action_assertion():
    assert resolve(IDLE, animation="sword_idle")["animation"] == "sword_idle"
    with pytest.raises(ValueError, match="does not match profile action"):
        resolve(IDLE, animation="gale_slash")


def test_unknown_camera_fails_fast():
    with pytest.raises(ValueError, match="unknown cameras"):
        resolve(GALE, cameras="front_final,missing")


@pytest.mark.parametrize("command", ["build", "review"])
def test_gif_cli_option_defaults_off_and_enables_explicitly(command: str):
    parsed_default = cli_parser().parse_args(execution_argv(command))
    assert parsed_default.gif is False
    assert parsed_default.animation is None
    assert parsed_default.rig_profile is None
    assert parsed_default.character_profile is None
    assert parsed_default.joint_contract is None

    parsed_enabled = cli_parser().parse_args([*execution_argv(command), "--gif"])
    assert parsed_enabled.gif is True
