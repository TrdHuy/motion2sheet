from __future__ import annotations

import json
import queue
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from motion2sheet.motion.harness_anim_generator.contracts import AgentExit, ProviderEvent
from motion2sheet.motion.harness_anim_generator.events import EventClient


class FakeAgentSession:
    def __init__(self) -> None:
        self.session_id = "fake-session"
        self.pid = 4242
        self._done = threading.Event()
        self._code: int | None = None
        self._events: queue.Queue[ProviderEvent] = queue.Queue()
        self.error: Exception | None = None

    def finish(self, code: int = 0) -> None:
        self._code = code
        self._done.set()

    def emit_provider(self, event: ProviderEvent) -> None:
        self._events.put(event)

    def next_event(self, timeout: float = 0.1) -> ProviderEvent | None:
        try:
            return self._events.get(timeout=timeout)
        except queue.Empty:
            return None

    @property
    def streams_closed(self) -> bool:
        return self._done.is_set() and self._events.empty()

    def poll(self) -> int | None:
        return self._code if self._done.is_set() else None

    def wait(self, timeout: float | None = None) -> AgentExit:
        if not self._done.wait(timeout or 10):
            raise TimeoutError("fake agent did not finish")
        if self.error is not None:
            raise self.error
        assert self._code is not None
        return AgentExit(self._code)

    def terminate(self) -> None:
        self.finish(-15)


class FakeAgentProvider:
    def __init__(self, behavior) -> None:
        self.behavior = behavior
        self.requests = []
        self.sessions: list[FakeAgentSession] = []

    def start(self, request):
        self.requests.append(request)
        session = FakeAgentSession()
        self.sessions.append(session)

        def run() -> None:
            try:
                self.behavior(request, session)
            except Exception as exc:  # surfaced by session.wait
                session.error = exc
            finally:
                if not session._done.is_set():
                    session.finish(1 if session.error else 0)

        threading.Thread(target=run, name="fake-agent", daemon=True).start()
        return session


def client_for(request) -> EventClient:
    return EventClient(
        run_id=request.run_id,
        event_url=request.event_url,
        token=request.event_token,
        state_path=request.workspace / ".fake-sequence",
        backoff_seconds=0.001,
    )


def create_outputs(workspace: Path, marker: bytes = b"v1") -> dict[str, str]:
    final = workspace / "final"
    final.mkdir(parents=True, exist_ok=True)
    values = {
        "animation": ("animation.json", b'{"opaque":"' + marker + b'"}'),
        "metadata": ("metadata.json", b'{"opaque":"metadata"}'),
        "preview": ("preview.gif", b"GIF89a" + marker),
    }
    result = {}
    for key, (name, data) in values.items():
        path = final / name
        path.write_bytes(data)
        result[key] = str(path.relative_to(workspace))
    return result


def post_json(url: str, token: str, body: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


@pytest.fixture
def repo_with_skill(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    skill = root / "skills" / "humanoid-motion-local-authoring"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Real test skill\n\nFollow every domain step.\n", encoding="utf-8")
    (skill / "skill.json").write_text(
        json.dumps(
            {
                "id": "humanoid-motion-local-authoring",
                "version": 1,
                "steps": [
                    {"id": "understand-intent", "title": "Understand motion intent"},
                    {"id": "discover-references", "title": "Discover references"},
                    {"id": "refine", "title": "Refine animation"},
                    {"id": "finalize", "title": "Produce final artifacts"},
                ],
            }
        ),
        encoding="utf-8",
    )
    return root
