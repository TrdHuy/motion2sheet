from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from motion2sheet.motion.harness_anim_generator.contracts import HarnessError
from motion2sheet.motion.harness_anim_generator.references import ReferenceLibrary


ROOT = Path(__file__).resolve().parents[3]
REFERENCE_ROOT = ROOT / "sample" / "humanoid_motion" / "mixamo"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_discovers_current_mixamo_contract_without_mutation():
    metadata_paths = sorted(REFERENCE_ROOT.glob("*/metadata.json"))
    before = {path: _sha256(path) for path in metadata_paths}
    references = ReferenceLibrary(REFERENCE_ROOT).discover()
    assert len(references) == len(metadata_paths) > 0
    assert all(reference.preview_path.is_file() for reference in references)
    assert all(reference.animation["id"] == reference.name for reference in references)
    assert {path: _sha256(path) for path in metadata_paths} == before


def test_reference_selection_is_deterministic_and_maps_metadata():
    library = ReferenceLibrary(REFERENCE_ROOT)
    first = library.select("dual weapon combo")
    second = library.select("dual weapon combo")
    assert first.animation_hash == second.animation_hash
    assert first.name == "dual-weapon-combo"
    assert first.score > 0
    assert first.metadata["intent"]


def test_malformed_reference_fails_closed(tmp_path):
    directory = tmp_path / ("a" * 64)
    directory.mkdir()
    (directory / "metadata.json").write_text(json.dumps({"name": "broken"}), encoding="utf-8")
    with pytest.raises(HarnessError, match="missing files"):
        ReferenceLibrary(tmp_path).discover()
