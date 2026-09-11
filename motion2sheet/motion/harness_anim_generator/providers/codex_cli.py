from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ..contracts import ProviderError, ProviderRequest, ProviderResponse


class CodexCLIProvider:
    def __init__(
        self,
        *,
        repo_root: Path,
        executable: str = "codex",
        timeout_seconds: int = 600,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.executable = executable
        self.timeout_seconds = timeout_seconds

    def _command(self, request: ProviderRequest, schema_path: Path) -> list[str]:
        command = [self.executable, "exec"]
        for attachment in request.attachments:
            command.extend(["--image", str(attachment.resolve())])
        command.extend([
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--json",
            "--output-schema",
            str(schema_path),
        ])
        command.append("-")
        return command

    @staticmethod
    def _stdin(request: ProviderRequest) -> str:
        return json.dumps(
            {
                "operation": request.operation,
                "instruction": request.instruction,
                "context": request.context,
            },
            ensure_ascii=False,
            allow_nan=False,
        )

    @staticmethod
    def _parse_stdout(stdout: str) -> dict[str, Any]:
        final_message: str | None = None
        for line_number, line in enumerate(stdout.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ProviderError(f"Codex CLI returned malformed JSONL on line {line_number}") from exc
            if not isinstance(event, dict):
                raise ProviderError(f"Codex CLI JSONL line {line_number} must be an object")
            if event.get("type") in {"error", "turn.failed"}:
                raise ProviderError(f"Codex CLI reported {event.get('type')}: {event}")
            item = event.get("item")
            if (
                event.get("type") == "item.completed"
                and isinstance(item, dict)
                and item.get("type") == "agent_message"
                and isinstance(item.get("text"), str)
            ):
                final_message = item["text"]
        if final_message is None:
            raise ProviderError("Codex CLI response did not contain a completed agent message")
        try:
            payload = json.loads(final_message)
        except json.JSONDecodeError as exc:
            raise ProviderError("Codex CLI final message is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise ProviderError("Codex CLI final JSON response must be an object")
        return payload

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        with tempfile.TemporaryDirectory(prefix="motion2sheet-codex-") as temporary:
            schema_path = Path(temporary) / "response.schema.json"
            schema_path.write_text(
                json.dumps(request.response_schema, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            command = self._command(request, schema_path)
            try:
                completed = subprocess.run(
                    command,
                    cwd=self.repo_root,
                    input=self._stdin(request),
                    text=True,
                    capture_output=True,
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except FileNotFoundError as exc:
                raise ProviderError(f"Codex CLI executable not found: {self.executable}") from exc
            except subprocess.TimeoutExpired as exc:
                raise ProviderError(
                    f"Codex CLI timed out after {self.timeout_seconds} seconds"
                ) from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "no diagnostic output"
            raise ProviderError(f"Codex CLI exited with code {completed.returncode}: {detail}")
        payload = self._parse_stdout(completed.stdout)
        return ProviderResponse(
            payload=payload,
            stdout=completed.stdout,
            stderr=completed.stderr,
            exit_code=completed.returncode,
        )
