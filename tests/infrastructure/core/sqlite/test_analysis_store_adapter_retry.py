"""Proves SqliteAnalysisStoreAdapter actually wires the T1/T3 writes
through retry_critical_write (Error_Handling_and_Resilience.md): a
transient sqlite3.OperationalError on the underlying store is retried and
recovers; if every attempt fails, the Analysis is never marked `failed` on
that basis -- the exception simply propagates so it never gets silently
lost, and no partial state is left in the database (SQLite's own
transaction atomicity, already guaranteed by the raw store's BEGIN
IMMEDIATE/ROLLBACK discipline).
"""

from __future__ import annotations

import sqlite3

import pytest

from sentinel.core.domain.analysis.entities import Analysis
from sentinel.infrastructure.core.sqlite.analysis_store import SqliteAnalysisStore
from sentinel.infrastructure.core.sqlite.analysis_store_adapter import SqliteAnalysisStoreAdapter


def _analysis(analysis_id: str = "an-1", correlation_id: str = "corr-1") -> Analysis:
    return Analysis.start(
        id=analysis_id, correlation_id=correlation_id, trigger_mode="mode_a", repository_id="repo-1",
        policy_version_id="policy-1-v1", artifacts=(), created_at="t0", scanner_executions=[],
    )


def test_create_or_get_recovers_from_a_transient_operational_error(sqlite_conn, seeded_repository_id, monkeypatch) -> None:
    raw_store = SqliteAnalysisStore(sqlite_conn)
    adapter = SqliteAnalysisStoreAdapter(raw_store)

    real_create_analysis = raw_store.create_analysis
    calls = {"count": 0}

    def flaky_create_analysis(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise sqlite3.OperationalError("database is locked")
        return real_create_analysis(*args, **kwargs)

    monkeypatch.setattr(raw_store, "create_analysis", flaky_create_analysis)

    persisted_id = adapter.create_or_get(_analysis())

    assert persisted_id == "an-1"
    assert calls["count"] == 2
    assert raw_store.get_analysis("an-1") is not None


def test_create_or_get_raises_after_exhausting_retries_never_marks_failed(sqlite_conn, monkeypatch) -> None:
    raw_store = SqliteAnalysisStore(sqlite_conn)
    adapter = SqliteAnalysisStoreAdapter(raw_store)

    def always_fails(*args, **kwargs):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(raw_store, "create_analysis", always_fails)

    with pytest.raises(sqlite3.OperationalError):
        adapter.create_or_get(_analysis(analysis_id="an-2", correlation_id="corr-2"))

    # No row of any kind exists -- not 'failed', not partially written.
    assert raw_store.get_analysis("an-2") is None
