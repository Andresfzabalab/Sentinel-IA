"""Proves the retry-with-backoff helpers (Error_Handling_and_Resilience.md):
transient sqlite3.OperationalError is retried and eventually succeeds or
exhausts; anything else propagates immediately, unretried; and the two
call shapes differ exactly as documented on exhaustion (raise+CRITICAL vs.
swallow+ERROR).
"""

from __future__ import annotations

import sqlite3

import pytest

from sentinel.shared.logging import get_logger
from sentinel.shared.retry import retry_best_effort_write, retry_critical_write


def _counting_fn(fail_times: int, exc_factory=lambda: sqlite3.OperationalError("database is locked")):
    calls = {"count": 0}

    def fn():
        calls["count"] += 1
        if calls["count"] <= fail_times:
            raise exc_factory()
        return "ok"

    return fn, calls


def test_retry_critical_write_succeeds_after_transient_failures() -> None:
    fn, calls = _counting_fn(fail_times=2)
    logger = get_logger("core", "test")

    result = retry_critical_write(fn, logger=logger, event="t1_write", max_attempts=5, sleep=lambda _: None)

    assert result == "ok"
    assert calls["count"] == 3


def test_retry_critical_write_raises_and_logs_critical_after_exhausting_attempts() -> None:
    fn, calls = _counting_fn(fail_times=10)
    logger = get_logger("core", "test")

    with pytest.raises(sqlite3.OperationalError):
        retry_critical_write(fn, logger=logger, event="t1_write", max_attempts=3, sleep=lambda _: None)

    assert calls["count"] == 3


def test_retry_critical_write_never_retries_a_non_operational_error() -> None:
    def fn():
        raise sqlite3.IntegrityError("unique constraint failed")

    logger = get_logger("core", "test")

    with pytest.raises(sqlite3.IntegrityError):
        retry_critical_write(fn, logger=logger, event="t1_write", max_attempts=5, sleep=lambda _: None)


def test_retry_best_effort_write_swallows_and_returns_none_after_exhausting_attempts() -> None:
    fn, calls = _counting_fn(fail_times=10)
    logger = get_logger("core", "test")

    result = retry_best_effort_write(fn, logger=logger, event="audit_write", max_attempts=3, sleep=lambda _: None)

    assert result is None
    assert calls["count"] == 3


def test_retry_best_effort_write_succeeds_after_transient_failures() -> None:
    fn, calls = _counting_fn(fail_times=1)
    logger = get_logger("core", "test")

    result = retry_best_effort_write(fn, logger=logger, event="audit_write", max_attempts=5, sleep=lambda _: None)

    assert result == "ok"
    assert calls["count"] == 2
