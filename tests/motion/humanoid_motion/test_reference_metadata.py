from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
REFERENCE_ROOT = REPO_ROOT / "sample" / "humanoid_motion"
REQUIRED_FIELDS = {
    "intent",
    "style",
    "characterType",
    "breakdown",
    "notes",
}


def _require_non_empty_string(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")


def validate_reference_metadata(document: object) -> None:
    if not isinstance(document, dict):
        raise ValueError("metadata root must be a JSON object")

    keys = set(document)
    missing = REQUIRED_FIELDS - keys
    extra = keys - REQUIRED_FIELDS
    if missing:
        raise ValueError(f"metadata is missing required fields: {sorted(missing)}")
    if extra:
        raise ValueError(f"metadata contains unsupported fields: {sorted(extra)}")

    _require_non_empty_string(document["intent"], "intent")
    _require_non_empty_string(document["style"], "style")

    if document["characterType"] != "humanoid":
        raise ValueError("characterType must be exactly 'humanoid'")

    for field in ("breakdown", "notes"):
        values = document[field]
        if not isinstance(values, list) or not values:
            raise ValueError(f"{field} must be a non-empty ordered list")
        for index, value in enumerate(values):
            _require_non_empty_string(value, f"{field}[{index}]")


def _valid_metadata() -> dict[str, object]:
    return {
        "intent": "strong straight punch",
        "style": "game combat",
        "characterType": "humanoid",
        "breakdown": [
            "starts from guard",
            "loads through the hips and torso",
            "extends the striking arm",
            "recovers toward guard",
        ],
        "notes": [
            "body rotation contributes to the strike",
            "follow-through stays controlled",
        ],
    }


def test_reference_metadata_contract_accepts_minimal_valid_document() -> None:
    validate_reference_metadata(_valid_metadata())


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda data: data.pop("intent"), "missing required fields"),
        (lambda data: data.__setitem__("mainActionSide", "Right"), "unsupported fields"),
        (lambda data: data.__setitem__("intent", "   "), "intent must be a non-empty string"),
        (lambda data: data.__setitem__("characterType", "animal"), "characterType must be exactly 'humanoid'"),
        (lambda data: data.__setitem__("breakdown", []), "breakdown must be a non-empty ordered list"),
        (lambda data: data.__setitem__("notes", ["ok", ""]), "notes[1] must be a non-empty string"),
    ],
)
def test_reference_metadata_contract_rejects_invalid_documents(mutate, message: str) -> None:
    document = _valid_metadata()
    mutate(document)
    with pytest.raises(ValueError, match=re.escape(message)):
        validate_reference_metadata(document)


def test_committed_humanoid_reference_samples_have_complete_companions() -> None:
    if not REFERENCE_ROOT.exists():
        return

    animation_files = sorted(REFERENCE_ROOT.rglob("animation.json"))
    metadata_files = sorted(REFERENCE_ROOT.rglob("metadata.json"))

    for animation_path in animation_files:
        relative = animation_path.relative_to(REFERENCE_ROOT)
        assert len(relative.parts) == 3, (
            "trusted Humanoid reference samples must use "
            "sample/humanoid_motion/<source>/<clip>/animation.json: "
            f"{relative}"
        )

        preview_path = animation_path.with_name("preview.gif")
        assert preview_path.is_file(), f"missing preview.gif next to {relative}"
        assert preview_path.stat().st_size > 0, f"empty preview.gif next to {relative}"

        metadata_path = animation_path.with_name("metadata.json")
        assert metadata_path.is_file(), f"missing metadata.json next to {relative}"

        try:
            document = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            pytest.fail(f"invalid JSON in {metadata_path.relative_to(REPO_ROOT)}: {exc}")

        try:
            validate_reference_metadata(document)
        except ValueError as exc:
            pytest.fail(f"invalid {metadata_path.relative_to(REPO_ROOT)}: {exc}")

    for metadata_path in metadata_files:
        animation_path = metadata_path.with_name("animation.json")
        assert animation_path.is_file(), (
            f"orphan metadata.json without animation.json: {metadata_path.relative_to(REPO_ROOT)}"
        )
