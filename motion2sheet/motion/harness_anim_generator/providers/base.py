from __future__ import annotations

from typing import Protocol

from ..contracts import AgentExit, AgentRunRequest, ProviderEvent


class AgentSession(Protocol):
    session_id: str
    pid: int | None

    def next_event(self, timeout: float = 0.1) -> ProviderEvent | None:
        """Return a pushed provider observation, or None if none is ready."""

    @property
    def streams_closed(self) -> bool:
        """Whether provider stdout and stderr have both reached EOF."""

    def poll(self) -> int | None:
        """Return the exit code once the process has terminated."""

    def wait(self, timeout: float | None = None) -> AgentExit:
        """Wait for the provider process to terminate."""

    def terminate(self) -> None:
        """Request process termination."""


class AgentProvider(Protocol):
    def start(self, request: AgentRunRequest) -> AgentSession:
        """Launch an autonomous agent with skill, task, history, and event ingress."""
