from __future__ import annotations

import threading
import time
from typing import Callable

from .contracts import ProviderEvent
from .events import RunState
from .providers.base import AgentSession


class ProviderEventPump:
    """Forwards passive provider observations without polling domain progress."""

    def __init__(self, session: AgentSession, submit: Callable[[ProviderEvent], int]) -> None:
        self.session = session
        self.submit = submit
        self._thread = threading.Thread(target=self._run, name=f"provider-{session.session_id}", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def join(self, timeout: float = 5.0) -> bool:
        self._thread.join(timeout)
        return not self._thread.is_alive()

    @property
    def is_running(self) -> bool:
        return self._thread.is_alive()

    def _run(self) -> None:
        while True:
            event = self.session.next_event(timeout=0.1)
            if event is not None:
                self.submit(event)
                continue
            if self.session.streams_closed and self.session.poll() is not None:
                return


class LivenessTicker:
    """Publishes generic liveness transitions without polling agent domain progress."""

    def __init__(
        self,
        session: AgentSession,
        state: RunState,
        submit: Callable[[str, dict[str, object]], int],
        *,
        interval_seconds: float = 1.0,
    ) -> None:
        self.session = session
        self.state = state
        self.submit = submit
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name=f"liveness-{session.session_id}",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout)

    @property
    def is_running(self) -> bool:
        return self._thread.is_alive()

    def _run(self) -> None:
        pending: str | None = None
        while not self._stop.wait(self.interval_seconds):
            desired = self.state.desired_liveness(process_alive=self.session.poll() is None)
            if desired is None:
                return
            current = self.state.current_liveness()
            if desired == current:
                pending = None
                continue
            if desired == pending:
                continue
            self.submit(
                "runtime.liveness.changed",
                {
                    "previous": current,
                    "state": desired,
                    "observedAtMonotonic": time.monotonic(),
                },
            )
            pending = desired
