from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import VfxSpec, load_profile as _load_profile


EFFECT_NAME = "splash"


def load_profile(path: Path) -> dict[str, Any]:
    return _load_profile(path)


def create_spec(**kwargs) -> VfxSpec:
    return VfxSpec.create(**kwargs)
