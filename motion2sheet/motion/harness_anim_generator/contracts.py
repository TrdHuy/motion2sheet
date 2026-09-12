from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping


JsonObject = Mapping[str, Any]
EventSource = Literal["agent_push", "provider", "harness"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class HarnessError(RuntimeError):
    """Base error raised by the SDAR runtime."""


class SkillError(HarnessError):
    """The configured skill authority could not be loaded."""


class ProviderError(HarnessError):
    """The configured agent provider could not run a session."""


class OutputContractError(HarnessError):
    """The agent did not declare usable final files."""


@dataclass(frozen=True)
class GenerationRequest:
    prompt: str
    provider: str
    output: Path
    resume_run_id: str | None = None
    report_port: int = 0
    open_report: bool = True
    skill_directory: Path | None = None
    keep_report_server: bool = False

    def __post_init__(self) -> None:
        prompt = self.prompt.strip()
        provider = self.provider.strip()
        if not prompt:
            raise ValueError("generation prompt must not be empty")
        if not provider:
            raise ValueError("provider must not be empty")
        if isinstance(self.report_port, bool) or not isinstance(self.report_port, int):
            raise ValueError("report_port must be an integer")
        if not 0 <= self.report_port <= 65535:
            raise ValueError("report_port must be between 0 and 65535")
        resume = self.resume_run_id.strip() if self.resume_run_id is not None else None
        if resume is not None and (not resume or "/" in resume or "\\" in resume or resume in {".", ".."}):
            raise ValueError("resume_run_id must be a single run identifier")
        object.__setattr__(self, "prompt", prompt)
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "output", Path(self.output))
        object.__setattr__(
            self,
            "skill_directory",
            Path(self.skill_directory) if self.skill_directory is not None else None,
        )
        object.__setattr__(self, "resume_run_id", resume)


@dataclass(frozen=True)
class SkillStep:
    id: str
    title: str


@dataclass(frozen=True)
class SkillManifest:
    id: str
    version: int
    steps: tuple[SkillStep, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "steps": [{"id": step.id, "title": step.title} for step in self.steps],
        }


@dataclass(frozen=True)
class LoadedSkill:
    directory: Path
    text: str
    manifest: SkillManifest


@dataclass(frozen=True)
class AgentRunRequest:
    run_id: str
    prompt: str
    skill_text: str
    skill_manifest: SkillManifest
    repository: Path
    workspace: Path
    history: JsonObject
    event_url: str
    event_token: str = field(repr=False)
    notify_command: Path


@dataclass(frozen=True)
class ProviderEvent:
    event_type: str
    payload: JsonObject
    raw: JsonObject | str | None = None
    stream: Literal["stdout", "stderr"] = "stdout"
    timestamp: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class AgentExit:
    exit_code: int
    ended_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class RuntimeEvent:
    event_id: str
    run_id: str
    event_type: str
    payload: JsonObject
    source: EventSource
    receive_order: int
    timestamp: str
    received_at: str
    sequence: int | None = None
    iteration: int | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "eventId": self.event_id,
            "runId": self.run_id,
            "type": self.event_type,
            "source": self.source,
            "receiveOrder": self.receive_order,
            "timestamp": self.timestamp,
            "receivedAt": self.received_at,
            "payload": dict(self.payload),
        }
        if self.sequence is not None:
            result["sequence"] = self.sequence
        if self.iteration is not None:
            result["iteration"] = self.iteration
        return result


@dataclass(frozen=True)
class GenerationResult:
    run_id: str
    status: Literal["completed"]
    output: Path
    animation_path: Path
    metadata_path: Path
    preview_path: Path
    workspace: Path
    report_path: Path
    report_url: str
    parent_run_id: str | None
