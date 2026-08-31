from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnimationDefinition:
    name: str
    runtime_module: str
    blender_author: str


DEFAULT_ANIMATION = "gale_slash"

_ANIMATIONS = {
    "gale_slash": AnimationDefinition(
        name="gale_slash",
        runtime_module="motion2sheet.anim2sheet.animations.gale_slash.animation",
        blender_author="animations/gale_slash/blender/author.py",
    ),
}


def animation_names() -> tuple[str, ...]:
    return tuple(sorted(_ANIMATIONS))


def get_animation(name: str) -> AnimationDefinition:
    try:
        return _ANIMATIONS[name]
    except KeyError as exc:
        raise ValueError(f"Unsupported animation: {name}") from exc
