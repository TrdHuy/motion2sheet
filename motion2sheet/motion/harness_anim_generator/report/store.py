from __future__ import annotations

import threading
import time
from copy import deepcopy
from typing import Any


class ProcessedEventStore:
    """Thread-safe store shared by the reducer and SSE clients.

    Publishing only appends in memory and wakes waiters, so a slow browser can
    never delay the event processor.
    """

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._events: list[dict[str, Any]] = []

    def publish(self, event: dict[str, Any]) -> None:
        with self._condition:
            self._events.append(deepcopy(event))
            self._condition.notify_all()

    def snapshot(self) -> list[dict[str, Any]]:
        with self._condition:
            return deepcopy(self._events)

    def wait_after(
        self,
        cursor: int,
        *,
        timeout: float = 15.0,
    ) -> tuple[list[dict[str, Any]], int]:
        deadline = time.monotonic() + timeout
        with self._condition:
            while len(self._events) <= cursor:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return [], cursor
                self._condition.wait(remaining)
            events = deepcopy(self._events[cursor:])
            return events, len(self._events)
