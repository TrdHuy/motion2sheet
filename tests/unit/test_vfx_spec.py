import pytest

from motion2sheet.vfx.cli import parser
from motion2sheet.vfx.spec import VfxSpec, parse_set


def test_cli_defaults_are_deterministic():
    args = parser().parse_args([
        "build",
        "--template", "slash",
        "--variant", "lightning",
        "--output", "build/vfx",
    ])
    assert args.frames == 8
    assert args.fps == 12
    assert args.canvas == (512, 512)
    assert args.sheet_columns == 4
    assert args.seed == 42891
    assert args.set_values == []


def test_spec_applies_known_overrides():
    spec = VfxSpec.create(
        template="slash",
        variant="lightning",
        frames=8,
        fps=12,
        canvas=(512, 512),
        sheet_columns=4,
        seed=1234,
        overrides=["radius=1.8", "sparks.count=30"],
    )
    assert spec.params["radius"] == pytest.approx(1.8)
    assert spec.params["sparks.count"] == 30


def test_unknown_override_is_rejected():
    with pytest.raises(ValueError, match="Unknown VFX parameter"):
        parse_set("foo.bar=1")


def test_integer_override_rejects_fraction():
    with pytest.raises(ValueError, match="must be an integer"):
        parse_set("sparks.count=1.5")


def test_out_of_range_override_is_rejected_by_spec():
    with pytest.raises(ValueError, match="must be in range"):
        VfxSpec.create(
            template="slash",
            variant="lightning",
            frames=8,
            fps=12,
            canvas=(512, 512),
            sheet_columns=4,
            seed=1,
            overrides=["radius=99"],
        )


def test_spec_round_trip():
    original = VfxSpec.create(
        template="slash",
        variant="lightning",
        frames=8,
        fps=12,
        canvas=(512, 512),
        sheet_columns=4,
        seed=42891,
    )
    restored = VfxSpec.from_dict(original.to_dict())
    assert restored == original
