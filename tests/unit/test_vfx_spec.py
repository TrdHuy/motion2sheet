import json

import pytest

from motion2sheet.vfx.cli import parser
from motion2sheet.vfx.spec import VfxSpec, load_profile, parse_set


def test_cli_accepts_profile_and_defers_build_defaults_to_spec():
    args = parser().parse_args([
        "build",
        "--profile", "profiles/vfx/lightning_slash_contract.json",
        "--output", "build/vfx",
    ])
    assert args.profile == "profiles/vfx/lightning_slash_contract.json"
    assert args.frames is None
    assert args.fps is None
    assert args.canvas is None
    assert args.sheet_columns is None
    assert args.seed is None
    assert args.set_values == []


def test_spec_defaults_are_deterministic_without_profile():
    spec = VfxSpec.create(template="slash", variant="lightning")
    assert spec.frames == 8
    assert spec.fps == 12
    assert spec.canvas == (512, 512)
    assert spec.sheet_columns == 4
    assert spec.seed == 42891


def test_spec_applies_known_numeric_and_color_overrides():
    spec = VfxSpec.create(
        template="slash",
        variant="lightning",
        seed=1234,
        overrides=[
            "radius=1.8",
            "sparks.count=30",
            "colors.outer=#1234AB",
            "lightning.major_count=5",
            "lightning.width_jitter=0.42",
            "lightning.tip_width=0.25",
        ],
    )
    assert spec.params["radius"] == pytest.approx(1.8)
    assert spec.params["sparks.count"] == 30
    assert spec.params["colors.outer"] == "#1234AB"
    assert spec.params["lightning.major_count"] == 5
    assert spec.params["lightning.width_jitter"] == pytest.approx(0.42)
    assert spec.params["lightning.tip_width"] == pytest.approx(0.25)


def test_old_parameter_aliases_remain_supported():
    spec = VfxSpec.create(
        template="slash",
        variant="lightning",
        overrides=["core.intensity=12", "glow.intensity=5", "lightning.branches=18"],
    )
    assert spec.params["intensity.core"] == pytest.approx(12)
    assert spec.params["intensity.outer"] == pytest.approx(5)
    assert spec.params["lightning.branch_count"] == 18


def test_profile_is_overridden_by_explicit_args_then_set(tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps({
        "template": "slash",
        "variant": "lightning",
        "fps": 10,
        "seed": 7,
        "colors": {"outer": "#2244FF"},
        "lightning": {
            "branch_count": 12,
            "jitter": 0.2,
            "major_count": 3,
            "major_width_min": 2.0,
            "major_width_max": 4.0,
        },
    }), encoding="utf-8")
    profile = load_profile(profile_path)
    spec = VfxSpec.create(
        profile=profile,
        fps=14,
        seed=99,
        overrides=[
            "lightning.branch_count=26",
            "lightning.major_count=6",
            "lightning.major_width_max=5.5",
            "colors.outer=#1028FF",
        ],
    )
    assert spec.fps == 14
    assert spec.seed == 99
    assert spec.params["lightning.branch_count"] == 26
    assert spec.params["lightning.major_count"] == 6
    assert spec.params["lightning.major_width_min"] == pytest.approx(2.0)
    assert spec.params["lightning.major_width_max"] == pytest.approx(5.5)
    assert spec.params["lightning.jitter"] == pytest.approx(0.2)
    assert spec.params["colors.outer"] == "#1028FF"


def test_nested_params_object_is_supported():
    spec = VfxSpec.create(
        profile={
            "template": "slash",
            "variant": "lightning",
            "params": {
                "shape": {"edge_noise": 1.9},
                "lightning": {
                    "secondary_branch_count": 16,
                    "width_smoothness": 0.8,
                    "branch_depth": 2,
                },
            },
        },
    )
    assert spec.params["shape.edge_noise"] == pytest.approx(1.9)
    assert spec.params["lightning.secondary_branch_count"] == 16
    assert spec.params["lightning.width_smoothness"] == pytest.approx(0.8)
    assert spec.params["lightning.branch_depth"] == 2


def test_hierarchical_lightning_width_bounds_are_validated():
    with pytest.raises(ValueError, match="major_width_min"):
        VfxSpec.create(
            template="slash",
            variant="lightning",
            overrides=["lightning.major_width_min=6", "lightning.major_width_max=4"],
        )
    with pytest.raises(ValueError, match="tip_width"):
        VfxSpec.create(
            template="slash",
            variant="lightning",
            overrides=["lightning.tip_width=6", "lightning.major_width_max=5"],
        )


def test_unknown_override_is_rejected():
    with pytest.raises(ValueError, match="Unknown VFX parameter"):
        parse_set("foo.bar=1")


def test_invalid_color_override_is_rejected():
    with pytest.raises(ValueError, match="must be a #RRGGBB color"):
        parse_set("colors.outer=blue")


def test_integer_override_rejects_fraction():
    with pytest.raises(ValueError, match="must be an integer"):
        parse_set("sparks.count=1.5")


def test_hierarchical_count_override_rejects_fraction():
    with pytest.raises(ValueError, match="must be an integer"):
        parse_set("lightning.major_count=4.5")


def test_out_of_range_override_is_rejected_immediately():
    with pytest.raises(ValueError, match="must be in range"):
        VfxSpec.create(
            template="slash",
            variant="lightning",
            overrides=["radius=99"],
        )


def test_spec_round_trip():
    original = VfxSpec.create(template="slash", variant="lightning")
    restored = VfxSpec.from_dict(original.to_dict())
    assert restored == original
