"""EventBusPort -- Internal Domain port, scoped to Sentinel Core only
(docs/02_Domain/Ports_and_Interfaces.md). An in-process pub/sub instance;
never a cross-module infrastructure port -- the AI & Agent Module has its
own, private instance, and the only thing that legitimately crosses is the
single-event AnalysisCompletedRelay (built in Phase 9).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any, Protocol

Handler = Callable[[dict[str, Any]], None]


class EventBusPort(Protocol):
    def publish(self, event_type: str, payload: dict[str, Any]) -> None: ...

    def subscribe(self, event_type: str, handler: Handler) -> None: ...


class InMemoryEventBus:
    """Synchronous, in-process pub/sub. A handler exception never aborts
    the publisher -- it is caught and swallowed here, since the Orchestrator
    calling `publish()` must not be able to fail because of an unrelated
    subscriber (mirrors P-09's independent-failure-isolation spirit, applied
    to in-process event handlers).
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        for handler in self._handlers.get(event_type, []):
            try:
                handler(payload)
            except Exception:  # noqa: BLE001 -- a subscriber's failure must never break publishing
                continue

    def subscribe(self, event_type: str, handler: Handler) -> None:
        self._handlers[event_type].append(handler)
