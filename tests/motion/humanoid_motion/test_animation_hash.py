from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from motion2sheet.motion.humanoid_motion import animation_hash, read_animation_hash
from motion2sheet.motion.humanoid_motion.schema import (
    ANIMATION_SCHEMA,
    EXPECTED_COORDINATE_SYSTEM,
    EXPECTED_QUATERNION_CONVENTION,
    ROTATION_JOINTS,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
REFERENCE_ROOT = REPO_ROOT / "sample" / "humanoid_motion" / "mixamo"
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_FILES = {"animation.json", "preview.gif", "metadata.json"}


def _animation() -> dict:
    identity = [1.0, 0.0, 0.0, 0.0]
    return {
        "schema": ANIMATION_SCHEMA,
        "version": 1,
        "id": "source-name",
        "canonicalSkeleton": "humanoid_v1",
        "durationSeconds": 1.0 / 30.0,
        "fps": 30.0,
        "frameCount": 2,
        "loop": True,
        "coordinateSystem": copy.deepcopy(EXPECTED_COORDINATE_SYSTEM),
        "quaternionConvention": copy.deepcopy(EXPECTED_QUATERNION_CONVENTION),
        "root": {
            "translations": [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
            "rotations": [identity[:], identity[:]],
        },
        "hips": {
            "translations": [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
            "rotations": [identity[:], identity[:]],
        },
        "joints": {
            semantic: {"rotations": [identity[:], identity[:]]}
            for semantic in ROTATION_JOINTS
        },
    }


def _reverse_object_keys(value):
    if isinstance(value, dict):
        return {
            key: _reverse_object_keys(child)
            for key, child in reversed(tuple(value.items()))
        }
    if isinstance(value, list):
        return [_reverse_object_keys(child) for child in value]
    return value


def test_semantic_hash_ignores_json_formatting_and_key_order(tmp_path: Path) -> None:
    animation = _animation()
    pretty = tmp_path / "pretty.json"
    compact = tmp_path / "compact.json"
    pretty.write_text(json.dumps(animation, indent=4) + "\n", encoding="utf-8")
    compact.write_text(
        json.dumps(_reverse_object_keys(animation), separators=(",", ":")),
        encoding="utf-8",
    )

    assert read_animation_hash(pretty) == read_animation_hash(compact)


def test_semantic_hash_ignores_animation_id() -> None:
    original = _animation()
    changed = copy.deepcopy(original)
    changed["id"] = "different-source-filename"

    assert animation_hash(original) == animation_hash(changed)


def test_semantic_hash_excludes_loop_and_root_translation() -> None:
    original = _animation()
    changed = copy.deepcopy(original)
    changed["loop"] = False
    changed["root"]["translations"][1][0] = 1e-9

    assert animation_hash(original) == animation_hash(changed)


def test_semantic_hash_changes_with_motion_value() -> None:
    original = _animation()
    changed = copy.deepcopy(original)
    changed["hips"]["translations"][1][0] = 0.25

    assert animation_hash(original) != animation_hash(changed)


def test_committed_mixamo_samples_match_semantic_hash_layout() -> None:
    samples = sorted(REFERENCE_ROOT.iterdir())
    assert samples
    assert all(path.is_dir() for path in samples)

    names = set()
    for sample in samples:
        assert HASH_RE.fullmatch(sample.name), sample
        assert {path.name for path in sample.iterdir()} == REQUIRED_FILES, sample
        assert all((sample / name).stat().st_size > 0 for name in REQUIRED_FILES), sample
        assert read_animation_hash(sample / "animation.json") == sample.name

        metadata = json.loads((sample / "metadata.json").read_text(encoding="utf-8"))
        assert isinstance(metadata, dict), sample
        assert isinstance(metadata.get("name"), str) and metadata["name"].strip(), sample
        assert metadata["name"] not in names, sample
        names.add(metadata["name"])
