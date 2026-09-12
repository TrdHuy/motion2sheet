from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import HarnessError


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HarnessError(f"cannot read previous run data {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise HarnessError(f"previous run data must be an object: {path}")
    return value


def load_resume_history(workspace_root: Path, run_id: str | None) -> dict[str, Any]:
    if run_id is None:
        return {}
    root = Path(workspace_root).resolve()
    previous = (root / run_id).resolve()
    if previous.parent != root or not previous.is_dir():
        raise HarnessError(f"previous run does not exist: {run_id}")
    request = _read_object(previous / "request.json")
    run = _read_object(previous / "run.json")
    history = _read_object(previous / "history.json")
    inherited_prompt = request.get("history", {}).get("originalPrompt")
    return {
        "parentRunId": run_id,
        "originalPrompt": inherited_prompt or request.get("prompt"),
        "run": run,
        "history": history,
        "iterationSummaries": history.get("iterations", []),
        "artifactPaths": history.get("artifacts", []),
        "evidencePaths": history.get("evidence", []),
        "previousFinalOutputs": {
            name: str((previous / "final" / filename).resolve())
            for name, filename in {
                "animation": "animation.json",
                "metadata": "metadata.json",
                "preview": "preview.gif",
            }.items()
            if (previous / "final" / filename).is_file()
        },
    }
