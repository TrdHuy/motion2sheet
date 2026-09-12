from __future__ import annotations

import fcntl
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import confined_file
from .contracts import (
    HarnessError,
    MemorySecurityError,
    SkillManifest,
    WorkspacePathSecurityError,
    utc_now,
)
from .redaction import SecretRedactor


MAX_PROPOSAL_BYTES = 1024 * 1024
MAX_PROPOSAL_ENTRIES = 50
MAX_LIST_ITEMS = 32
MAX_SHORT_TEXT = 128
MAX_STATEMENT_TEXT = 4096
MAX_LOCATOR_TEXT = 2048
MAX_INJECTED_MEMORY_ENTRIES = 32
MAX_INJECTED_MEMORY_BYTES = 65_536
MEMORY_SELECTION_POLICY = "newest-fit-first-chronological-output"


class MemoryProposalError(HarnessError):
    """An optional memory proposal did not satisfy the generic contract."""


class MemoryStoreError(HarnessError):
    """The persistent memory bank is unreadable or corrupt."""


def _safe_segment(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value) and value not in {".", ".."}:
        return value
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.") or "namespace"
    return f"{slug[:80]}-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:12]}"


def _text(value: Any, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MemoryProposalError(f"{label} must be a non-empty string")
    value = value.strip()
    if len(value) > maximum:
        raise MemoryProposalError(f"{label} exceeds {maximum} characters")
    return value


def _strings(value: Any, label: str, maximum: int, *, required: bool = False) -> list[str]:
    if not isinstance(value, list):
        raise MemoryProposalError(f"{label} must be an array")
    if len(value) > MAX_LIST_ITEMS:
        raise MemoryProposalError(f"{label} exceeds {MAX_LIST_ITEMS} items")
    if required and not value:
        raise MemoryProposalError(f"{label} must contain at least one item")
    return [_text(item, f"{label}[{index}]", maximum) for index, item in enumerate(value)]


def _locator(value: str, label: str) -> str:
    if "\\" in value:
        raise MemoryProposalError(f"{label} must use a relative POSIX-style locator")
    path = PurePosixPath(value.split("#", 1)[0])
    if path.is_absolute() or ".." in path.parts:
        raise MemoryProposalError(f"{label} must not be absolute or contain '..'")
    return value


def _entry(value: Any, index: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MemoryProposalError(f"memory entry {index} must be an object")
    required = {"kind", "statement", "scope", "references", "evidence", "confidence"}
    allowed = required | {"id"}
    if not required.issubset(value) or not set(value).issubset(allowed):
        raise MemoryProposalError(
            f"memory entry {index} must contain kind, statement, scope, references, "
            "evidence and confidence, with optional id"
        )
    result: dict[str, Any] = {
        "kind": _text(value["kind"], f"memory entry {index} kind", MAX_SHORT_TEXT),
        "statement": _text(
            value["statement"], f"memory entry {index} statement", MAX_STATEMENT_TEXT
        ),
        "scope": _strings(
            value["scope"], f"memory entry {index} scope", MAX_SHORT_TEXT
        ),
        "references": [
            _locator(item, f"memory entry {index} references")
            for item in _strings(
                value["references"],
                f"memory entry {index} references",
                MAX_LOCATOR_TEXT,
            )
        ],
        "evidence": _strings(
            value["evidence"],
            f"memory entry {index} evidence",
            MAX_LOCATOR_TEXT,
            required=True,
        ),
        "confidence": _text(
            value["confidence"], f"memory entry {index} confidence", MAX_SHORT_TEXT
        ),
    }
    if result["confidence"] not in {"low", "medium", "high"}:
        raise MemoryProposalError(
            f"memory entry {index} confidence must be low, medium or high"
        )
    if "id" in value:
        result["id"] = _text(value["id"], f"memory entry {index} id", MAX_SHORT_TEXT)
    return result


def _entry_hash(entry: dict[str, Any]) -> str:
    canonical = json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ProviderMemoryBank:
    """Append-only, provider-private experience persisted by the SDAR runtime."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()

    def path_for(self, skill_id: str, provider: str) -> Path:
        return self.root / _safe_segment(skill_id) / _safe_segment(provider) / "entries.jsonl"

    def _store_path(self, skill_id: str, provider: str, *, create: bool) -> Path:
        current = self.root
        if create:
            current.mkdir(parents=True, exist_ok=True)
        if current.exists() and (current.is_symlink() or not current.is_dir()):
            raise MemorySecurityError(f"provider memory root must be a directory: {current}")
        for segment in (_safe_segment(skill_id), _safe_segment(provider)):
            current = current / segment
            if current.exists():
                if current.is_symlink() or not current.is_dir():
                    raise MemorySecurityError(
                        f"provider memory namespace must be a directory: {current}"
                    )
            elif create:
                current.mkdir()
        if not current.resolve(strict=False).is_relative_to(self.root):
            raise MemorySecurityError("provider memory namespace escapes memory root")
        return current / "entries.jsonl"

    def _read_archive(self, manifest: SkillManifest, provider: str) -> list[dict[str, Any]]:
        path = self._store_path(manifest.id, provider, create=False)
        records: list[dict[str, Any]] = []
        if path.exists():
            if path.is_symlink() or not path.is_file():
                raise MemorySecurityError(f"provider memory store must be a regular file: {path}")
            line_number = 0
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
                for line_number, line in enumerate(lines, 1):
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    if not isinstance(record, dict) or not isinstance(record.get("entryHash"), str):
                        raise ValueError("record must be an object with entryHash")
                    records.append(record)
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
                raise MemoryStoreError(
                    f"cannot load provider memory {path}: line {line_number}: {exc}"
                ) from exc
        return records

    @staticmethod
    def _working_payload(
        manifest: SkillManifest,
        provider: str,
        archive_count: int,
        entries: list[dict[str, Any]],
        *,
        truncated: bool,
    ) -> dict[str, Any]:
        return {
            "skillId": manifest.id,
            "skillVersion": manifest.version,
            "provider": provider,
            "archiveEntryCount": archive_count,
            "injectedEntryCount": len(entries),
            "truncated": truncated,
            "selectionPolicy": MEMORY_SELECTION_POLICY,
            "limits": {
                "maxEntries": MAX_INJECTED_MEMORY_ENTRIES,
                "maxBytes": MAX_INJECTED_MEMORY_BYTES,
            },
            "entries": entries,
        }

    @staticmethod
    def serialized_size(value: dict[str, Any]) -> int:
        return len(
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )

    def load(self, manifest: SkillManifest, provider: str) -> dict[str, Any]:
        archive = self._read_archive(manifest, provider)
        selected_newest_first: list[dict[str, Any]] = []
        for record in reversed(archive):
            if len(selected_newest_first) >= MAX_INJECTED_MEMORY_ENTRIES:
                break
            trial = list(reversed([*selected_newest_first, record]))
            payload = self._working_payload(
                manifest,
                provider,
                len(archive),
                trial,
                truncated=False,
            )
            if self.serialized_size(payload) <= MAX_INJECTED_MEMORY_BYTES:
                selected_newest_first.append(record)
        selected = list(reversed(selected_newest_first))
        payload = self._working_payload(
            manifest,
            provider,
            len(archive),
            selected,
            truncated=len(selected) != len(archive),
        )
        if self.serialized_size(payload) > MAX_INJECTED_MEMORY_BYTES:
            raise MemoryStoreError("provider working memory exceeds its serialized byte limit")
        return payload

    def persist_proposal(
        self,
        *,
        declared_path: str,
        agent_workspace: Path,
        run_id: str,
        manifest: SkillManifest,
        provider: str,
        redactor: SecretRedactor,
        reported_files: list[dict[str, object]],
    ) -> dict[str, Any]:
        try:
            source = confined_file(agent_workspace, declared_path, redactor)
        except WorkspacePathSecurityError as exc:
            raise MemorySecurityError(str(exc)) from exc
        except HarnessError as exc:
            raise MemoryProposalError(str(exc)) from exc
        if source.stat().st_size > MAX_PROPOSAL_BYTES:
            raise MemoryProposalError(
                f"memory proposal exceeds {MAX_PROPOSAL_BYTES} bytes: {declared_path}"
            )
        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise MemoryProposalError(f"cannot read memory proposal {declared_path}: {exc}") from exc
        raw = redactor.value(raw)
        if not isinstance(raw, dict) or set(raw) != {"entries"}:
            raise MemoryProposalError("memory proposal must contain exactly an entries array")
        entries = raw["entries"]
        if not isinstance(entries, list) or not entries:
            raise MemoryProposalError("memory proposal entries must be a non-empty array")
        if len(entries) > MAX_PROPOSAL_ENTRIES:
            raise MemoryProposalError(
                f"memory proposal exceeds {MAX_PROPOSAL_ENTRIES} entries"
            )
        normalized = [_entry(value, index) for index, value in enumerate(entries)]
        reported = {
            Path(path).resolve()
            for item in reported_files
            if item.get("eventType")
            in {"evidence.created", "artifact.created", "artifact.updated"}
            and isinstance(path := item.get("path"), str)
        }
        for index, entry in enumerate(normalized):
            for locator in entry["evidence"]:
                self._validate_evidence(
                    locator,
                    index=index,
                    agent_workspace=agent_workspace,
                    redactor=redactor,
                    reported=reported,
                )
        return self._append(
            normalized,
            run_id=run_id,
            manifest=manifest,
            provider=provider,
            redactor=redactor,
        )

    @staticmethod
    def _validate_evidence(
        locator: str,
        *,
        index: int,
        agent_workspace: Path,
        redactor: SecretRedactor,
        reported: set[Path],
    ) -> None:
        base = locator.split("#", 1)[0]
        label = f"memory entry {index} evidence {locator!r}"
        if not base or "\\" in base:
            raise MemoryProposalError(f"{label} must use a relative POSIX-style path")
        pure = PurePosixPath(base)
        if pure.is_absolute():
            raise MemorySecurityError(f"{label} must be inside the agent workspace")
        try:
            source = confined_file(agent_workspace, base, redactor)
        except WorkspacePathSecurityError as exc:
            raise MemorySecurityError(str(exc)) from exc
        except HarnessError as exc:
            raise MemoryProposalError(str(exc)) from exc
        if ".." in pure.parts:
            raise MemoryProposalError(f"{label} must not contain '..'")
        if source not in reported:
            raise MemoryProposalError(
                f"{label} was not reported with evidence.created, "
                "artifact.created or artifact.updated"
            )

    def _append(
        self,
        entries: list[dict[str, Any]],
        *,
        run_id: str,
        manifest: SkillManifest,
        provider: str,
        redactor: SecretRedactor,
    ) -> dict[str, Any]:
        path = self._store_path(manifest.id, provider, create=True)
        if path.exists() and (path.is_symlink() or not path.is_file()):
            raise MemorySecurityError(f"provider memory store must be a regular file: {path}")
        lock_path = path.with_name(".entries.lock")
        if lock_path.exists() and (lock_path.is_symlink() or not lock_path.is_file()):
            raise MemorySecurityError(
                f"provider memory lock must be a regular file: {lock_path}"
            )
        appended = 0
        duplicates = 0
        with lock_path.open("a", encoding="ascii") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            existing = self._read_archive(manifest, provider)
            hashes = {item["entryHash"] for item in existing}
            records = []
            for entry in entries:
                digest = _entry_hash(entry)
                if digest in hashes:
                    duplicates += 1
                    continue
                hashes.add(digest)
                records.append(
                    {
                        "runId": run_id,
                        "createdAt": utc_now(),
                        "provider": provider,
                        "skillId": manifest.id,
                        "skillVersion": manifest.version,
                        "entryHash": digest,
                        "entry": entry,
                    }
                )
            if records:
                with path.open("a", encoding="utf-8") as handle:
                    for record in records:
                        handle.write(
                            json.dumps(
                                redactor.value(record),
                                ensure_ascii=False,
                                sort_keys=True,
                            )
                            + "\n"
                        )
                    handle.flush()
                appended = len(records)
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        return {
            "path": str(path),
            "proposed": len(entries),
            "appended": appended,
            "duplicates": duplicates,
        }
