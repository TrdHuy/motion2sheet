from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from .schema import validate_animation


def _identity_payload(value: Any) -> dict[str, Any]:
    animation = validate_animation(copy.deepcopy(value))
    return {
        "durationSeconds": animation["durationSeconds"],
        "fps": animation["fps"],
        "frameCount": animation["frameCount"],
        "root": {"rotations": animation["root"]["rotations"]},
        "hips": {
            "translations": animation["hips"]["translations"],
            "rotations": animation["hips"]["rotations"],
        },
        "joints": {
            semantic: {"rotations": track["rotations"]}
            for semantic, track in animation["joints"].items()
        },
    }


def animation_hash(value: Any) -> str:
    """Return the semantic SHA-256 identity of a Humanoid Motion animation."""
    payload = _identity_payload(value)
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def read_animation_hash(path: Path) -> str:
    """Load, validate/normalize, and semantically hash an animation JSON file."""
    with path.open("r", encoding="utf-8") as handle:
        return animation_hash(json.load(handle))
