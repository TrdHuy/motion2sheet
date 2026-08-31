from __future__ import annotations

from pathlib import Path

import pytest

from motion2sheet.anim2sheet.animations.gale_slash.animation import resolve_review_request
from motion2sheet.anim2sheet.cli import parser as cli_parser
from motion2sheet.anim2sheet.registry import get_animation

ROOT = Path(__file__).resolve().parents[3]
PROFILE = ROOT / "profiles/anim2sheet/animations/gale_slash/animation.json5"
CONTRACT = ROOT / "profiles/anim2sheet/animations/gale_slash/joint_contract.json"
CAMERAS = ROOT / "profiles/anim2sheet/cameras/fast_keypose_review.json"


def resolve(*, frames=None, cameras=None):
    return resolve_review_request(
        profile_path=PROFILE,
        joint_contract_path=CONTRACT,
        camera_profile_path=CAMERAS,
        frames=frames,
        cameras=cameras,
    )


def execution_argv(command: str) -> list[str]:
    return [
        command,
        "--animation", "gale_slash",
        "--profile", str(PROFILE),
        "--joint-contract", str(CONTRACT),
        "--camera-profile", str(CAMERAS),
        "--output", "build/test",
    ]


def test_known_animation_resolves():
    definition = get_animation("gale_slash")
    assert definition.name == "gale_slash"
    assert definition.runtime_module.endswith("animations.gale_slash.animation")
    assert definition.blender_author == "animations/gale_slash/blender/author.py"


def test_unknown_animation_fails():
    with pytest.raises(ValueError, match="Unsupported animation"):
        get_animation("missing")


def test_review_without_frames_uses_contract_frames():
    request = resolve()
    assert request["executionFrames"] == list(range(1, 17))
    assert request["contractFrames"] == list(range(1, 17))


def test_review_single_frame_subset():
    request = resolve(frames="8")
    assert request["executionFrames"] == [8]
    assert request["contractFrames"] == list(range(1, 17))


def test_review_multi_frame_subset():
    assert resolve(frames="7,8")["executionFrames"] == [7, 8]


def test_review_frame_outside_contract_fails_fast():
    with pytest.raises(ValueError, match="outside contract"):
        resolve(frames="17")


def test_unknown_camera_fails_fast():
    with pytest.raises(ValueError, match="unknown cameras"):
        resolve(cameras="front_final,missing")


@pytest.mark.parametrize("command", ["build", "review"])
def test_gif_cli_option_defaults_off_and_enables_explicitly(command: str):
    parsed_default = cli_parser().parse_args(execution_argv(command))
    assert parsed_default.gif is False

    parsed_enabled = cli_parser().parse_args([*execution_argv(command), "--gif"])
    assert parsed_enabled.gif is True
