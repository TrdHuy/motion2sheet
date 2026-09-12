from __future__ import annotations

import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

from .contracts import HarnessError


@dataclass(frozen=True)
class RunWorkspace:
    root: Path
    agent: Path
    logs: Path
    iterations: Path
    final: Path
    report: Path
    notify_command: Path


def create_workspace(workspace_root: Path, run_id: str) -> RunWorkspace:
    root = (Path(workspace_root).resolve() / run_id).resolve()
    if root.exists():
        raise HarnessError(f"run workspace already exists: {root}")
    agent = root / "agent"
    logs = root / "logs"
    iterations = root / "iterations"
    final = root / "final"
    report = root / "report"
    for path in (agent, logs, iterations, final, report, agent / ".sdar" / "bin"):
        path.mkdir(parents=True, exist_ok=True)
    for name in ("events.jsonl", "provider-events.jsonl", "stdout.log", "stderr.log"):
        (logs / name).touch()
    notify = agent / ".sdar" / "bin" / "sdar-notify"
    notify.write_text(
        "#!/bin/sh\n"
        f"exec {sys.executable!r} -m motion2sheet.motion.harness_anim_generator.events notify \"$@\"\n",
        encoding="utf-8",
    )
    notify.chmod(notify.stat().st_mode | stat.S_IXUSR)
    return RunWorkspace(root, agent, logs, iterations, final, report, notify)


def preflight_output(output: Path) -> Path:
    output = Path(output).resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise HarnessError(f"output must not exist or must be an empty directory: {output}")
    return output


def graphical_environment() -> bool:
    if sys.platform in {"darwin", "win32"}:
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
