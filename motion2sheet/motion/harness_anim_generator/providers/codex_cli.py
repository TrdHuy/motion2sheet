from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any, Callable

from ..contracts import AgentExit, AgentRunRequest, ProviderError, ProviderEvent


def _provider_event(line: str, stream: str) -> ProviderEvent:
    line = line.rstrip("\n")
    if stream == "stderr":
        return ProviderEvent(
            "agent.log",
            {"level": "stderr", "message": line},
            raw=line,
            stream="stderr",
        )
    try:
        raw: Any = json.loads(line)
    except json.JSONDecodeError:
        return ProviderEvent(
            "agent.warning",
            {"message": "Codex emitted malformed JSONL"},
            raw=line,
        )
    if not isinstance(raw, dict):
        return ProviderEvent("agent.log", {"message": str(raw)}, raw=raw)
    provider_type = raw.get("type")
    item = raw.get("item") if isinstance(raw.get("item"), dict) else {}
    item_type = item.get("type")
    if provider_type == "item.started" and item_type == "command_execution":
        normalized = "command.started"
    elif provider_type == "item.completed" and item_type == "command_execution":
        normalized = "command.completed"
    elif provider_type == "item.completed" and item_type == "file_change":
        normalized = "artifact.updated"
    elif provider_type in {"error", "turn.failed"}:
        normalized = "agent.warning"
    else:
        normalized = "agent.log"
    return ProviderEvent(
        normalized,
        {"providerType": provider_type, "itemType": item_type},
        raw=raw,
    )


class CodexAgentSession:
    def __init__(self, process: subprocess.Popen[str]) -> None:
        self.process = process
        self.session_id = str(uuid.uuid4())
        self.pid = process.pid
        self._events: queue.Queue[ProviderEvent] = queue.Queue()
        self._open_streams = 2
        self._lock = threading.Lock()
        for name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
            thread = threading.Thread(
                target=self._read,
                args=(name, stream),
                name=f"codex-{name}-{self.session_id}",
                daemon=True,
            )
            thread.start()

    def _read(self, name: str, stream: Any) -> None:
        try:
            if stream is not None:
                for line in stream:
                    self._events.put(_provider_event(line, name))
        finally:
            with self._lock:
                self._open_streams -= 1

    @property
    def streams_closed(self) -> bool:
        with self._lock:
            return self._open_streams == 0

    def next_event(self, timeout: float = 0.1) -> ProviderEvent | None:
        try:
            return self._events.get(timeout=timeout)
        except queue.Empty:
            return None

    def poll(self) -> int | None:
        return self.process.poll()

    def wait(self, timeout: float | None = None) -> AgentExit:
        try:
            code = self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise ProviderError("Codex CLI session timed out") from exc
        return AgentExit(code)

    def terminate(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()


class CodexCLIProvider:
    def __init__(
        self,
        *,
        repo_root: Path,
        executable: str = "codex",
        popen_factory: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.executable = executable
        self.popen_factory = popen_factory

    def _command(self, request: AgentRunRequest) -> list[str]:
        return [
            self.executable,
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--sandbox",
            "workspace-write",
            "--json",
            "-c",
            "sandbox_workspace_write.network_access=true",
            "-c",
            "shell_environment_policy.inherit=all",
            "-c",
            "shell_environment_policy.ignore_default_excludes=true",
            "-C",
            str(request.repository),
            "-",
        ]

    @staticmethod
    def _prompt(request: AgentRunRequest) -> str:
        history = json.dumps(request.history, ensure_ascii=False, indent=2)
        manifest = json.dumps(request.skill_manifest.to_dict(), ensure_ascii=False, indent=2)
        return (
            "You are the domain-owning animation authoring agent in a Skill-Driven Agent Runtime.\n"
            "Use repository tools and motion2sheet directly. The harness only observes runtime events; "
            "it does not choose references, validate, render, review, refine, or create metadata.\n"
            f"Report semantic progress with the helper at {request.notify_command}. "
            "You must send the final completion declaration with that helper.\n\n"
            "ANIMATION AUTHORING SKILL (workflow authority; follow in full)\n"
            "=============================================================\n"
            f"{request.skill_text}\n\n"
            "SKILL OBSERVABILITY MANIFEST\n"
            "============================\n"
            f"{manifest}\n\n"
            "PREVIOUS READ-ONLY HISTORY\n"
            "==========================\n"
            f"{history}\n\n"
            "USER TASK\n"
            "=========\n"
            f"{request.prompt}\n\n"
            "RUNTIME OUTPUT LOCATION\n"
            "=======================\n"
            f"Create all run-owned files inside: {request.workspace}\n"
            "Do not put final outputs in the public output directory; declare their workspace paths.\n"
        )

    def start(self, request: AgentRunRequest) -> CodexAgentSession:
        environment = os.environ.copy()
        environment.update(
            {
                "HARNESS_RUN_ID": request.run_id,
                "HARNESS_EVENT_URL": request.event_url,
                "HARNESS_TOKEN": request.event_token,
                "HARNESS_EVENT_STATE": str(request.workspace / ".sdar" / "sequence"),
                "SDAR_NOTIFY": str(request.notify_command),
                "PATH": f"{request.notify_command.parent}{os.pathsep}{environment.get('PATH', '')}",
                "PYTHONPATH": f"{request.repository}{os.pathsep}{environment.get('PYTHONPATH', '')}",
            }
        )
        try:
            process = self.popen_factory(
                self._command(request),
                cwd=request.repository,
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as exc:
            raise ProviderError(f"Codex CLI executable not found: {self.executable}") from exc
        try:
            if process.stdin is None:
                raise ProviderError("Codex CLI stdin is unavailable")
            process.stdin.write(self._prompt(request))
            process.stdin.close()
        except (BrokenPipeError, OSError) as exc:
            process.terminate()
            raise ProviderError(f"could not send task to Codex CLI: {exc}") from exc
        return CodexAgentSession(process)
