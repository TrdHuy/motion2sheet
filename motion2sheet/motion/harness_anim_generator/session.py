from __future__ import annotations

import threading
from typing import Callable

from .contracts import ProviderEvent
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

    def _run(self) -> None:
        while True:
            event = self.session.next_event(timeout=0.1)
            if event is not None:
                self.submit(event)
                continue
            if self.session.streams_closed and self.session.poll() is not None:
                return
