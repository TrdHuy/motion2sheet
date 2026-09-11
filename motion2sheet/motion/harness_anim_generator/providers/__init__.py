from __future__ import annotations

from pathlib import Path

from ..contracts import HarnessError
from .base import AgentProvider, AgentSession
from .codex_cli import CodexCLIProvider


PROVIDER_NAMES = ("codex-cli",)


def create_provider(name: str, *, repo_root: Path) -> AgentProvider:
    if name == "codex-cli":
        return CodexCLIProvider(repo_root=repo_root)
    raise HarnessError(f"unknown animation generation provider: {name!r}")


__all__ = ["AgentProvider", "AgentSession", "CodexCLIProvider", "PROVIDER_NAMES", "create_provider"]
