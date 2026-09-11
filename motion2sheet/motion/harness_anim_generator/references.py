from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .contracts import HarnessError, SelectedReference


HASH_RE = re.compile(r"^[0-9a-f]{64}$")
TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
REQUIRED_FILES = ("animation.json", "metadata.json", "preview.gif")


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HarnessError(f"cannot read reference JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise HarnessError(f"reference JSON must contain an object: {path}")
    return value


def _tokens(value: str) -> set[str]:
    return set(TOKEN_RE.findall(value.casefold()))


def _all_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_all_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_all_text(item) for item in value)
    return ""


class ReferenceLibrary:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def discover(self) -> tuple[SelectedReference, ...]:
        if not self.root.is_dir():
            raise HarnessError(f"Humanoid Motion reference library does not exist: {self.root}")
        references: list[SelectedReference] = []
        for directory in sorted(self.root.iterdir(), key=lambda path: path.name):
            if not directory.is_dir():
                continue
            if not HASH_RE.fullmatch(directory.name):
                raise HarnessError(f"reference directory is not an animation hash: {directory}")
            missing = [name for name in REQUIRED_FILES if not (directory / name).is_file()]
            if missing:
                raise HarnessError(f"reference {directory.name} is missing files: {missing}")
            metadata = _read_object(directory / "metadata.json")
            animation = _read_object(directory / "animation.json")
            name = metadata.get("name")
            if not isinstance(name, str) or not name.strip():
                raise HarnessError(f"reference metadata name is missing: {directory / 'metadata.json'}")
            references.append(
                SelectedReference(
                    animation_hash=directory.name,
                    name=name.strip(),
                    score=0,
                    directory=directory.resolve(),
                    animation=animation,
                    metadata=metadata,
                    preview_path=(directory / "preview.gif").resolve(),
                )
            )
        if not references:
            raise HarnessError(f"Humanoid Motion reference library is empty: {self.root}")
        return tuple(references)

    @staticmethod
    def _score(prompt: str, reference: SelectedReference) -> int:
        query = _tokens(prompt)
        name = _tokens(reference.name)
        intent = _tokens(str(reference.metadata.get("intent", "")))
        metadata = _tokens(_all_text(reference.metadata))
        return 3 * len(query & name) + 2 * len(query & intent) + len(query & metadata)

    def select(self, prompt: str) -> SelectedReference:
        scored = [
            SelectedReference(
                animation_hash=reference.animation_hash,
                name=reference.name,
                score=self._score(prompt, reference),
                directory=reference.directory,
                animation=reference.animation,
                metadata=reference.metadata,
                preview_path=reference.preview_path,
            )
            for reference in self.discover()
        ]
        return min(scored, key=lambda item: (-item.score, item.name, item.animation_hash))
