from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthoringDefinition:
    capability: str
    blender_author: str


DEFAULT_AUTHORING_CAPABILITY = "humanoid_v2"

_AUTHORS = {
    "humanoid_v2": AuthoringDefinition(
        capability="humanoid_v2",
        blender_author="common/authoring/humanoid.py",
    ),
}


def authoring_capabilities() -> tuple[str, ...]:
    return tuple(sorted(_AUTHORS))


def get_authoring_capability(name: str) -> AuthoringDefinition:
    try:
        return _AUTHORS[name]
    except KeyError as exc:
        raise ValueError(f"Unsupported anim2sheet authoring capability: {name}") from exc
