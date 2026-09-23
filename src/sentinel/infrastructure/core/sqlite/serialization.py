"""Per-analysis_id serialization queue (stub for Phase 1, exercised for real in Phase 6).

Per docs/03_API/Persistence_Strategy.md's Concurrency Model: two T2
transactions for *different* Analyses must proceed independently; two T2
transactions for the *same* Analysis (e.g., two scanners finishing within
milliseconds of each other) must be serialized, one at a time, so the
"have all eligible Scanner Executions reached a terminal state?" check that
decides whether T3 should fire is never evaluated against a half-written
state. This is in-process only (Deployment_Strategy.md's single-process
modular monolith) -- no distributed lock is needed for the MVP.
"""

from __future__ import annotations

import threading
from collections import defaultdict


class AnalysisWriteQueue:
    """Hands out one lock per analysis_id, created lazily and reused.

    Two different analysis_ids never share a lock and therefore never
    block each other; the same analysis_id always gets the same lock
    instance for the lifetime of this queue.
    """

    def __init__(self) -> None:
        self._locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._locks_guard = threading.Lock()

    def lock_for(self, analysis_id: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks[analysis_id]
