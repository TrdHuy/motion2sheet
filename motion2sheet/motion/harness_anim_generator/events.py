from __future__ import annotations

import argparse
import fcntl
import json
import os
import queue
import threading
import time
import urllib.error
import urllib.request
import uuid
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from .artifacts import ArtifactRegistry
from .contracts import ProviderEvent, RuntimeEvent, SkillManifest, utc_now
from .redaction import SecretRedactor, append_jsonl, write_json
from .report.store import ProcessedEventStore


AGENT_EVENT_TYPES = frozenset(
    {
        "agent.started",
        "agent.heartbeat",
        "agent.log",
        "agent.warning",
        "skill.step.started",
        "skill.step.completed",
        "skill.step.skipped",
        "iteration.started",
        "iteration.completed",
        "command.started",
        "command.completed",
        "artifact.created",
        "artifact.updated",
        "artifact.read",
        "evidence.created",
        "memory.proposed",
        "agent.completed",
        "agent.failed",
    }
)


class EventEnvelopeError(ValueError):
    """A pushed event is not a valid generic SDAR envelope."""


@dataclass(frozen=True)
class AcceptResult:
    duplicate: bool
    receive_order: int | None


def _integer(value: Any, label: str, *, minimum: int = 0) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise EventEnvelopeError(f"{label} must be an integer >= {minimum}")
    return value


class RunEventBus:
    """One logically isolated FIFO queue and idempotency set per run."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.queue: queue.Queue[RuntimeEvent] = queue.Queue()
        self._lock = threading.Lock()
        self._event_ids: set[str] = set()
        self._receive_order = 0

    def _order(self) -> int:
        self._receive_order += 1
        return self._receive_order

    def accept_agent(self, envelope: Mapping[str, Any]) -> AcceptResult:
        event_id = envelope.get("eventId")
        run_id = envelope.get("runId")
        event_type = envelope.get("type")
        timestamp = envelope.get("timestamp")
        payload = envelope.get("payload", {})
        if not isinstance(event_id, str) or not event_id.strip():
            raise EventEnvelopeError("eventId must be a non-empty string")
        if run_id != self.run_id:
            raise EventEnvelopeError("runId does not match the event ingress")
        if not isinstance(event_type, str) or not event_type.strip():
            raise EventEnvelopeError("type must be a non-empty string")
        if not isinstance(timestamp, str) or not timestamp.strip():
            raise EventEnvelopeError("timestamp must be a non-empty string")
        try:
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise EventEnvelopeError("timestamp must be ISO-8601") from exc
        if not isinstance(payload, dict):
            raise EventEnvelopeError("payload must be an object")
        sequence = _integer(envelope.get("sequence"), "sequence")
        iteration = _integer(envelope.get("iteration"), "iteration", minimum=1)
        with self._lock:
            if event_id in self._event_ids:
                return AcceptResult(True, None)
            self._event_ids.add(event_id)
            order = self._order()
            event = RuntimeEvent(
                event_id=event_id,
                run_id=self.run_id,
                event_type=event_type,
                payload=payload,
                source="agent_push",
                receive_order=order,
                timestamp=timestamp,
                received_at=utc_now(),
                sequence=sequence,
                iteration=iteration,
            )
            self.queue.put_nowait(event)
        return AcceptResult(False, order)

    def submit_provider(self, event: ProviderEvent) -> int:
        payload = dict(event.payload)
        if event.raw is not None:
            payload["raw"] = event.raw
        payload["stream"] = event.stream
        return self._submit(event.event_type, payload, "provider", event.timestamp)

    def submit_harness(self, event_type: str, payload: Mapping[str, Any] | None = None) -> int:
        return self._submit(event_type, dict(payload or {}), "harness", utc_now())

    def _submit(self, event_type: str, payload: dict[str, Any], source: str, timestamp: str) -> int:
        with self._lock:
            order = self._order()
            event = RuntimeEvent(
                event_id=str(uuid.uuid4()),
                run_id=self.run_id,
                event_type=event_type,
                payload=payload,
                source=source,  # type: ignore[arg-type]
                receive_order=order,
                timestamp=timestamp,
                received_at=utc_now(),
            )
            self.queue.put_nowait(event)
            return order


def initial_run_state(
    *,
    run_id: str,
    parent_run_id: str | None,
    prompt: str,
    provider: str,
    manifest: SkillManifest,
) -> dict[str, Any]:
    return {
        "runId": run_id,
        "parentRunId": parent_run_id,
        "prompt": prompt,
        "provider": provider,
        "status": "starting",
        "agentAliveState": "starting",
        "processAlive": False,
        "pid": None,
        "exitCode": None,
        "startedAt": utc_now(),
        "completedAt": None,
        "lastActivity": None,
        "lastHeartbeat": None,
        "currentIteration": None,
        "skillManifest": manifest.to_dict(),
        "skillSteps": {},
        "iterations": {},
        "artifacts": [],
        "evidence": [],
        "warnings": [],
        "completion": None,
        "memoryProposal": None,
        "memoryPersistence": None,
        "failure": None,
    }


class RunState:
    def __init__(
        self,
        value: dict[str, Any],
        *,
        idle_seconds: float = 15.0,
        stalled_seconds: float = 60.0,
    ) -> None:
        if idle_seconds < 0 or stalled_seconds <= idle_seconds:
            raise ValueError("liveness thresholds must satisfy 0 <= idle < stalled")
        self._value = value
        self._lock = threading.Lock()
        self._idle_seconds = idle_seconds
        self._stalled_seconds = stalled_seconds
        self._last_activity_monotonic = time.monotonic()

    def apply(self, event: RuntimeEvent, registry: ArtifactRegistry) -> list[str]:
        warnings: list[str] = []
        with self._lock:
            value = self._value
            kind = event.event_type
            payload = dict(event.payload)
            if kind != "runtime.liveness.changed":
                value["lastActivity"] = event.received_at
                self._last_activity_monotonic = time.monotonic()
                if value["processAlive"] and value["status"] not in {"completed", "failed"}:
                    value["agentAliveState"] = "running"
            if kind == "run.started" and event.source == "harness":
                value["status"] = "running"
            elif kind == "runtime.process.started" and event.source == "harness":
                value["processAlive"] = True
                value["pid"] = payload.get("pid")
                value["agentAliveState"] = "running"
            elif kind == "runtime.process.exited" and event.source == "harness":
                value["processAlive"] = False
                value["exitCode"] = payload.get("exitCode")
            elif kind == "runtime.liveness.changed" and event.source == "harness":
                state = payload.get("state")
                if state in {"starting", "running", "idle", "possibly_stalled"}:
                    value["agentAliveState"] = state
            elif kind == "agent.started" and event.source == "agent_push":
                value["status"] = "running"
                value["agentAliveState"] = "running"
            elif kind == "agent.heartbeat" and event.source == "agent_push":
                value["lastHeartbeat"] = event.received_at
                value["agentAliveState"] = "running"
            elif kind == "agent.completed" and event.source == "agent_push":
                value["completion"] = payload
            elif kind == "agent.failed" and event.source == "agent_push":
                value["failure"] = payload or {"message": "agent reported failure"}
            elif kind == "memory.proposed" and event.source == "agent_push":
                if value["memoryProposal"] is not None:
                    warnings.append("multiple memory proposals reported; latest declaration retained")
                value["memoryProposal"] = {
                    "path": payload.get("path"),
                    "receiveOrder": event.receive_order,
                }
            elif kind == "memory.persisted" and event.source == "harness":
                value["memoryPersistence"] = {"status": "persisted", **payload}
            elif kind == "memory.rejected" and event.source == "harness":
                value["memoryPersistence"] = {"status": "rejected", **payload}
                warning = str(payload.get("message") or "memory proposal rejected")
                value["warnings"].append(warning)
            elif kind in {"run.completed", "run.failed"} and event.source == "harness":
                value["status"] = kind.split(".", 1)[1]
                value["agentAliveState"] = value["status"]
                value["completedAt"] = event.received_at
                if kind == "run.failed":
                    value["failure"] = payload
            elif kind.startswith("skill.step.") and event.source == "agent_push":
                warnings.extend(self._apply_skill(event))
            elif kind.startswith("iteration.") and event.source == "agent_push":
                warnings.extend(self._apply_iteration(event))
            elif (
                kind in {"artifact.created", "artifact.updated", "evidence.created"}
                and event.source == "agent_push"
            ):
                bucket = "evidence" if kind == "evidence.created" else "artifacts"
                try:
                    item = registry.snapshot(event, bucket)
                except Exception as exc:  # observation failure is not a domain gate
                    warnings.append(str(exc))
                else:
                    item.update(
                        {
                            "receiveOrder": event.receive_order,
                            "eventType": kind,
                            "source": event.source,
                        }
                    )
                    value[bucket].append(item)
            if event.sequence is not None and event.source == "agent_push":
                previous = value.get("lastAgentSequence")
                if previous is not None and event.sequence != previous + 1:
                    warnings.append(
                        f"agent_push sequence gap: expected {previous + 1}, received {event.sequence}"
                    )
                value["lastAgentSequence"] = event.sequence
            if warnings:
                value["warnings"].extend(warnings)
            if event.source == "agent_push" and kind not in AGENT_EVENT_TYPES:
                warning = f"unknown agent event type: {kind}"
                value["warnings"].append(warning)
                warnings.append(warning)
        return warnings

    def _iteration(self, event: RuntimeEvent) -> str:
        return str(event.iteration or self._value.get("currentIteration") or 0)

    def _apply_skill(self, event: RuntimeEvent) -> list[str]:
        step = event.payload.get("step")
        if not isinstance(step, str) or not step:
            return [f"malformed skill report at receiveOrder {event.receive_order}: missing step"]
        known = {item["id"] for item in self._value["skillManifest"]["steps"]}
        if step not in known:
            return [f"unknown skill step reported: {step}"]
        status = {
            "skill.step.started": "in_progress",
            "skill.step.completed": "completed",
            "skill.step.skipped": "skipped",
        }[event.event_type]
        iteration = self._iteration(event)
        steps = self._value["skillSteps"].setdefault(iteration, {})
        steps[step] = {
            "status": status,
            "summary": event.payload.get("summary"),
            "reason": event.payload.get("reason"),
            "receiveOrder": event.receive_order,
        }
        return []

    def _apply_iteration(self, event: RuntimeEvent) -> list[str]:
        if event.iteration is None:
            return [f"malformed iteration report at receiveOrder {event.receive_order}"]
        key = str(event.iteration)
        item = self._value["iterations"].setdefault(key, {"iteration": event.iteration})
        if event.event_type == "iteration.started":
            item.update(
                {
                    "status": "running",
                    "startedAt": event.received_at,
                    "reason": event.payload.get("reason"),
                }
            )
            self._value["currentIteration"] = event.iteration
        else:
            item.update(
                {
                    "status": "completed",
                    "completedAt": event.received_at,
                    "summary": event.payload.get("summary"),
                }
            )
            try:
                started = datetime.fromisoformat(item["startedAt"])
                completed = datetime.fromisoformat(event.received_at)
                item["durationSeconds"] = max(0.0, (completed - started).total_seconds())
            except (KeyError, TypeError, ValueError):
                pass
        return []

    def desired_liveness(self, *, process_alive: bool) -> str | None:
        """Return the observable liveness state without mutating persisted state."""

        with self._lock:
            if self._value["status"] in {"completed", "failed"} or not process_alive:
                return None
            idle_for = time.monotonic() - self._last_activity_monotonic
            if idle_for >= self._stalled_seconds:
                return "possibly_stalled"
            if idle_for >= self._idle_seconds:
                return "idle"
            return "running"

    def current_liveness(self) -> str:
        with self._lock:
            return str(self._value["agentAliveState"])

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._value)


class EventProcessor:
    def __init__(
        self,
        *,
        bus: RunEventBus,
        state: RunState,
        registry: ArtifactRegistry,
        store: ProcessedEventStore,
        run_path: Path,
        history_path: Path,
        events_path: Path,
        provider_events_path: Path,
        stdout_path: Path,
        stderr_path: Path,
        redactor: SecretRedactor,
        processing_hook: Callable[[RuntimeEvent], None] | None = None,
    ) -> None:
        self.bus = bus
        self.state = state
        self.registry = registry
        self.store = store
        self.run_path = run_path
        self.history_path = history_path
        self.events_path = events_path
        self.provider_events_path = provider_events_path
        self.stdout_path = stdout_path
        self.stderr_path = stderr_path
        self.redactor = redactor
        self.processing_hook = processing_hook
        self._stop = threading.Event()
        self._error: Exception | None = None
        self._thread = threading.Thread(target=self._run, name=f"sdar-events-{bus.run_id}", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def drain(self) -> None:
        self.bus.queue.join()

    @property
    def error(self) -> Exception | None:
        return self._error

    @property
    def is_running(self) -> bool:
        return self._thread.is_alive()

    def stop(self) -> None:
        self.drain()
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set() or not self.bus.queue.empty():
            try:
                event = self.bus.queue.get(timeout=0.05)
            except queue.Empty:
                continue
            try:
                if self.processing_hook is not None:
                    self.processing_hook(event)
                sanitized = replace(event, payload=self.redactor.value(dict(event.payload)))
                serialized = sanitized.to_dict()
                append_jsonl(self.events_path, serialized, self.redactor)
                self._persist_provider(event)
                warnings = self.state.apply(sanitized, self.registry)
                snapshot = self.state.snapshot()
                write_json(self.run_path, snapshot, self.redactor)
                write_json(self.history_path, self._history(snapshot), self.redactor)
                self.store.publish(self.redactor.value(serialized))
                for warning in warnings:
                    self.bus.submit_harness("agent.warning", {"message": warning})
            except Exception as exc:  # retain a terminal runtime error for the supervisor
                self._error = exc
            finally:
                self.bus.queue.task_done()

    def _persist_provider(self, event: RuntimeEvent) -> None:
        if event.source != "provider":
            return
        append_jsonl(self.provider_events_path, event.to_dict(), self.redactor)
        stream = event.payload.get("stream")
        raw = event.payload.get("raw")
        if raw is None:
            return
        line = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
        target = self.stderr_path if stream == "stderr" else self.stdout_path
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(self.redactor.text(line) + "\n")

    @staticmethod
    def _history(state: dict[str, Any]) -> dict[str, Any]:
        iterations = []
        for item in state["iterations"].values():
            iteration = item["iteration"]
            enriched = dict(item)
            enriched["skillSteps"] = state["skillSteps"].get(str(iteration), {})
            enriched["artifacts"] = [
                artifact for artifact in state["artifacts"] if artifact["iteration"] == iteration
            ]
            enriched["evidence"] = [
                evidence for evidence in state["evidence"] if evidence["iteration"] == iteration
            ]
            iterations.append(enriched)
        return {
            "runId": state["runId"],
            "parentRunId": state["parentRunId"],
            "iterations": iterations,
            "skillSteps": state["skillSteps"],
            "artifacts": state["artifacts"],
            "evidence": state["evidence"],
            "warnings": state["warnings"],
            "completion": state["completion"],
            "memoryProposal": state["memoryProposal"],
            "memoryPersistence": state["memoryPersistence"],
        }


class EventClient:
    """Stable agent-facing emitter with idempotent retries and monotonic sequence."""

    def __init__(
        self,
        *,
        run_id: str,
        event_url: str,
        token: str,
        state_path: Path,
        attempts: int = 4,
        backoff_seconds: float = 0.1,
    ) -> None:
        self.run_id = run_id
        self.event_url = event_url
        self.token = token
        self.state_path = Path(state_path)
        self.attempts = attempts
        self.backoff_seconds = backoff_seconds

    def _next_sequence(self) -> int:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.state_path.with_name(f".{self.state_path.name}.lock")
        with lock_path.open("a", encoding="ascii") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                try:
                    current = int(self.state_path.read_text(encoding="ascii"))
                except (OSError, ValueError):
                    current = 0
                value = current + 1
                temporary = self.state_path.with_name(
                    f".{self.state_path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
                )
                temporary.write_text(str(value), encoding="ascii")
                temporary.replace(self.state_path)
                return value
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def send(
        self,
        event_type: str,
        *,
        payload: Mapping[str, Any] | None = None,
        iteration: int | None = None,
    ) -> dict[str, Any]:
        envelope: dict[str, Any] = {
            "eventId": str(uuid.uuid4()),
            "runId": self.run_id,
            "sequence": self._next_sequence(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "payload": dict(payload or {}),
        }
        if iteration is not None:
            envelope["iteration"] = iteration
        body = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.event_url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        last_error: Exception | None = None
        for attempt in range(self.attempts):
            try:
                with urllib.request.urlopen(request, timeout=3) as response:
                    if response.status != 202:
                        raise RuntimeError(f"event ingress returned HTTP {response.status}")
                    return envelope
            except urllib.error.HTTPError as exc:
                if exc.code < 500:
                    raise RuntimeError(f"event ingress rejected notification: HTTP {exc.code}") from exc
                last_error = exc
                if attempt + 1 < self.attempts:
                    time.sleep(self.backoff_seconds * (2**attempt))
            except (OSError, urllib.error.URLError) as exc:
                last_error = exc
                if attempt + 1 < self.attempts:
                    time.sleep(self.backoff_seconds * (2**attempt))
        raise RuntimeError(f"could not notify SDAR event ingress: {last_error}")


def _notification(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sdar-notify")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("skill-start", "skill-complete", "skill-skip"):
        item = sub.add_parser(name)
        item.add_argument("step")
        item.add_argument("--iteration", type=int)
        item.add_argument("--summary")
        item.add_argument("--reason")
    for name in ("iteration-start", "iteration-complete"):
        item = sub.add_parser(name)
        item.add_argument("iteration", type=int)
        item.add_argument("--reason")
        item.add_argument("--summary")
    for name in ("artifact-created", "artifact-updated", "artifact-read", "evidence-created"):
        item = sub.add_parser(name)
        item.add_argument("path")
        item.add_argument("--iteration", type=int)
    memory = sub.add_parser("memory-update")
    memory.add_argument("path")
    sub.add_parser("started")
    for name in ("log", "warning"):
        item = sub.add_parser(name)
        item.add_argument("message")
    for name in ("command-start", "command-complete"):
        item = sub.add_parser(name)
        item.add_argument("command")
        item.add_argument("--exit-code", type=int)
    complete = sub.add_parser("complete")
    complete.add_argument("--animation", required=True)
    complete.add_argument("--metadata", required=True)
    complete.add_argument("--preview", required=True)
    failure = sub.add_parser("fail")
    failure.add_argument("--message", required=True)
    heartbeat = sub.add_parser("heartbeat")
    heartbeat.add_argument("--message")
    args = parser.parse_args(argv)
    mapping = {
        "skill-start": "skill.step.started",
        "skill-complete": "skill.step.completed",
        "skill-skip": "skill.step.skipped",
        "iteration-start": "iteration.started",
        "iteration-complete": "iteration.completed",
        "artifact-created": "artifact.created",
        "artifact-updated": "artifact.updated",
        "artifact-read": "artifact.read",
        "evidence-created": "evidence.created",
        "memory-update": "memory.proposed",
        "complete": "agent.completed",
        "fail": "agent.failed",
        "heartbeat": "agent.heartbeat",
        "started": "agent.started",
        "log": "agent.log",
        "warning": "agent.warning",
        "command-start": "command.started",
        "command-complete": "command.completed",
    }
    command = args.command
    payload = {
        key: value
        for key, value in vars(args).items()
        if key not in {"command", "iteration"} and value is not None
    }
    if command == "complete":
        payload = {"outputs": payload}
    client = EventClient(
        run_id=os.environ["HARNESS_RUN_ID"],
        event_url=os.environ["HARNESS_EVENT_URL"],
        token=os.environ["HARNESS_TOKEN"],
        state_path=Path(os.environ["HARNESS_EVENT_STATE"]),
    )
    client.send(mapping[command], payload=payload, iteration=getattr(args, "iteration", None))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("notify",))
    args, remaining = parser.parse_known_args(argv)
    if args.mode == "notify":
        return _notification(remaining)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
