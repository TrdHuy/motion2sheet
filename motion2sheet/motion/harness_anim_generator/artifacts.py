from __future__ import annotations

import shutil
from pathlib import Path

from .contracts import HarnessError, RuntimeEvent
from .redaction import SecretRedactor


def owned_file(agent_workspace: Path, declared: str, redactor: SecretRedactor) -> Path:
    if not isinstance(declared, str) or not declared.strip():
        raise HarnessError("artifact path must be a non-empty string")
    if redactor.text(declared) != declared:
        raise HarnessError("artifact path contains a runtime secret")
    raw = Path(declared)
    candidate = raw if raw.is_absolute() else Path(agent_workspace) / raw
    root = Path(agent_workspace).resolve()
    lexical = candidate.resolve(strict=False)
    if not lexical.is_relative_to(root):
        raise HarnessError(f"artifact escapes agent workspace: {declared}")
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise HarnessError(f"artifact does not exist: {declared}") from exc
    if not resolved.is_relative_to(root):
        raise HarnessError(f"artifact escapes agent workspace: {declared}")
    if candidate.is_symlink() or not resolved.is_file():
        raise HarnessError(f"artifact must be a regular non-symlink file: {declared}")
    if redactor.contains_file(resolved):
        raise HarnessError(f"artifact contains a runtime secret: {declared}")
    return resolved


class ArtifactRegistry:
    def __init__(self, *, agent_workspace: Path, iterations: Path, redactor: SecretRedactor) -> None:
        self.agent_workspace = Path(agent_workspace)
        self.iterations = Path(iterations)
        self.redactor = redactor

    def snapshot(self, event: RuntimeEvent, kind: str) -> dict[str, object]:
        declared = event.payload.get("path")
        source = owned_file(self.agent_workspace, declared, self.redactor)
        iteration = event.iteration or 0
        target_dir = self.iterations / f"v{iteration}" / kind
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{event.receive_order:08d}-{source.name}"
        shutil.copyfile(source, target)
        return {
            "path": str(source),
            "snapshot": str(target),
            "name": source.name,
            "iteration": iteration,
        }
