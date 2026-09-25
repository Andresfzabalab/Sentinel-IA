"""Retry-with-backoff for SQLite writes (Error_Handling_and_Resilience.md's
"SQLite write failure" rows). Only `sqlite3.OperationalError` is treated as
transient/retryable -- a local disk-full or a held OS-level lock, expected
to be rare and to clear on its own. `sqlite3.IntegrityError` and anything
else is a logic-level failure that will never succeed on retry, so it
always propagates immediately, unretried.

Two call shapes, matching the two rows in the Failure Catalog:
- `retry_critical_write` -- T1/T3 (verdict-critical). Exhausted retries are
  logged `CRITICAL` and re-raised; the caller must never mark the Analysis
  `failed` on this basis -- it stays `running` until the write eventually
  succeeds (manually retried or via the next recovery sweep).
- `retry_best_effort_write` -- secondary tables (Audit/Notify/Agent/
  Knowledge). Exhausted retries are logged `ERROR` and swallowed (returns
  `None`) -- this must never block or raise back into the primary flow.
"""

from __future__ import annotations

import sqlite3
import time
from typing import Callable, TypeVar

from sentinel.shared.logging import SentinelLogger

T = TypeVar("T")

_MAX_ATTEMPTS = 5
_BASE_DELAY_SECONDS = 0.05


def retry_critical_write(
    fn: Callable[[], T],
    *,
    logger: SentinelLogger,
    event: str,
    correlation_id: str | None = None,
    analysis_id: str | None = None,
    max_attempts: int = _MAX_ATTEMPTS,
    base_delay_seconds: float = _BASE_DELAY_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    last_exc: sqlite3.OperationalError | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except sqlite3.OperationalError as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                sleep(base_delay_seconds * (2**attempt))

    logger.critical(
        event,
        f"verdict-critical SQLite write failed after {max_attempts} attempts: {last_exc}",
        correlation_id=correlation_id,
        analysis_id=analysis_id,
    )
    raise last_exc  # type: ignore[misc]


def retry_best_effort_write(
    fn: Callable[[], T],
    *,
    logger: SentinelLogger,
    event: str,
    correlation_id: str | None = None,
    analysis_id: str | None = None,
    max_attempts: int = _MAX_ATTEMPTS,
    base_delay_seconds: float = _BASE_DELAY_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> T | None:
    last_exc: sqlite3.OperationalError | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except sqlite3.OperationalError as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                sleep(base_delay_seconds * (2**attempt))

    logger.error(
        event,
        f"secondary-table SQLite write failed after {max_attempts} attempts, giving up: {last_exc}",
        correlation_id=correlation_id,
        analysis_id=analysis_id,
    )
    return None
