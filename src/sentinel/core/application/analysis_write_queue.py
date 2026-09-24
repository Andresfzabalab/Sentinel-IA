"""Per-analysis_id serialization queue.

Per docs/03_API/Persistence_Strategy.md's Concurrency Model: two T2
transactions for *different* Analyses must proceed independently; two T2
transactions for the *same* Analysis (e.g., two scanners finishing within
milliseconds of each other) must be serialized, one at a time, so the
"have all eligible Scanner Executions reached a terminal state?" check is
never evaluated against a half-written state. This lives in
core/application/ (moved here in Phase 6, not infrastructure/) because it
is pure in-process concurrency control with no infrastructure dependency
at all -- the Orchestrator (P-01/P-06) may depend on it directly.

Known scope boundary: this only serializes writes for the *same*
analysis_id within one process. It does not by itself make two genuinely
different Analyses' concurrent writes to a shared SQLite connection safe
from a lower-level hazard (overlapping transactions issued by different
threads on one Connection object) -- that would require a
connection-per-thread/pool redesign, which is out of Phase 6's stated
scope (Implementation_Strategy.md): Phase 6 exercises this queue for real,
concurrent *scanner completions within one Analysis*, which is exactly
what it protects.
"""

from __future__ import annotations

import threading


class AnalysisWriteQueue:
    """Hands out one lock per analysis_id, created lazily and reused.

    Two different analysis_ids never share a lock and therefore never
    block each other; the same analysis_id always gets the same lock
    instance for the lifetime of this queue.
    """

    def __init__(self) -> None:
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def lock_for(self, analysis_id: str) -> threading.Lock:
        with self._locks_guard:
            if analysis_id not in self._locks:
                self._locks[analysis_id] = threading.Lock()
            return self._locks[analysis_id]
