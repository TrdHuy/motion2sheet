from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


REDACTED = "[REDACTED]"


class SecretRedactor:
    def __init__(self, secret: str) -> None:
        if not secret:
            raise ValueError("redaction secret must not be empty")
        self._secret = secret
        self._secret_bytes = secret.encode("utf-8")

    def text(self, value: str) -> str:
        return value.replace(self._secret, REDACTED)

    def value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, list):
            return [self.value(item) for item in value]
        if isinstance(value, tuple):
            return [self.value(item) for item in value]
        if isinstance(value, dict):
            return {self.text(str(key)): self.value(item) for key, item in value.items()}
        return value

    def contains_file(self, path: Path) -> bool:
        overlap = max(0, len(self._secret_bytes) - 1)
        tail = b""
        with Path(path).open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                data = tail + chunk
                if self._secret_bytes in data:
                    return True
                tail = data[-overlap:] if overlap else b""
        return False

    def scrub_file(self, path: Path) -> bool:
        path = Path(path)
        if path.is_symlink() or not path.is_file():
            return False
        data = path.read_bytes()
        if self._secret_bytes not in data:
            return False
        path.write_bytes(data.replace(self._secret_bytes, REDACTED.encode("utf-8")))
        return True

    def scrub_tree(self, root: Path) -> list[Path]:
        scrubbed: list[Path] = []
        root = Path(root)
        if not root.exists():
            return scrubbed
        for directory, names, files in os.walk(root, followlinks=False):
            names[:] = [name for name in names if not (Path(directory) / name).is_symlink()]
            for name in files:
                path = Path(directory) / name
                if self.scrub_file(path):
                    scrubbed.append(path)
        return scrubbed


def write_json(path: Path, value: Any, redactor: SecretRedactor) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(redactor.value(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def append_jsonl(path: Path, value: Any, redactor: SecretRedactor) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(redactor.value(value), ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
