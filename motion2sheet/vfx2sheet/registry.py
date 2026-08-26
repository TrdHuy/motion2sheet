from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EffectDefinition:
    name: str
    runtime_module: str
    renderer: str


DEFAULT_EFFECT = "splash"

_EFFECTS = {
    "splash": EffectDefinition(
        name="splash",
        runtime_module="motion2sheet.vfx2sheet.effects.splash.effect",
        renderer="effects/splash/blender/renderer.py",
    ),
}


def effect_names() -> tuple[str, ...]:
    return tuple(sorted(_EFFECTS))


def get_effect(name: str) -> EffectDefinition:
    try:
        return _EFFECTS[name]
    except KeyError as exc:
        raise ValueError(f"Unsupported VFX effect: {name}") from exc
