"""Proves SqliteAuditStore.find()'s filter combinations (UC-6, Phase 8)."""

from __future__ import annotations

import pytest

from sentinel.infrastructure.core.sqlite.audit_store import AuditRecordCreate, SqliteAuditStore


def _record(**overrides) -> AuditRecordCreate:
    defaults = dict(
        id="audit-1", actor="system", event_type="AnalysisCompleted", origin="sentinel-core",
        payload="{}", created_at="2026-01-01T00:00:00Z",
    )
    defaults.update(overrides)
    return AuditRecordCreate(**defaults)


@pytest.fixture()
def two_seeded_analysis_ids(sqlite_conn, seeded_repository_id) -> tuple[str, str]:
    """audit_record.subject_analysis_id has an intra-module FK to
    analysis(id) -- these two rows exist purely so that FK is satisfied."""
    for analysis_id in ("an-1", "an-2"):
        sqlite_conn.execute(
            "INSERT INTO analysis (id, correlation_id, trigger_mode, repository_id, policy_version_id, status, created_at) "
            "VALUES (?, ?, 'mode_a', 'repo-1', 'policy-1-v1', 'completed', 't0')",
            (analysis_id, f"corr-{analysis_id}"),
        )
    return "an-1", "an-2"


def test_find_with_no_filters_returns_everything(sqlite_conn) -> None:
    store = SqliteAuditStore(sqlite_conn)
    store.append(_record(id="a1"))
    store.append(_record(id="a2"))

    assert len(store.find()) == 2


def test_find_by_analysis_id(sqlite_conn, two_seeded_analysis_ids) -> None:
    store = SqliteAuditStore(sqlite_conn)
    store.append(_record(id="a1", subject_analysis_id="an-1"))
    store.append(_record(id="a2", subject_analysis_id="an-2"))

    results = store.find(analysis_id="an-1")

    assert [r["id"] for r in results] == ["a1"]


def test_find_by_correlation_id(sqlite_conn) -> None:
    store = SqliteAuditStore(sqlite_conn)
    store.append(_record(id="a1", correlation_id="corr-1"))
    store.append(_record(id="a2", correlation_id="corr-2"))

    results = store.find(correlation_id="corr-2")

    assert [r["id"] for r in results] == ["a2"]


def test_find_by_date_range(sqlite_conn) -> None:
    store = SqliteAuditStore(sqlite_conn)
    store.append(_record(id="a1", created_at="2026-01-01T00:00:00Z"))
    store.append(_record(id="a2", created_at="2026-01-05T00:00:00Z"))
    store.append(_record(id="a3", created_at="2026-01-10T00:00:00Z"))

    results = store.find(from_ts="2026-01-02T00:00:00Z", to_ts="2026-01-09T00:00:00Z")

    assert [r["id"] for r in results] == ["a2"]


def test_find_combines_filters_with_and(sqlite_conn, two_seeded_analysis_ids) -> None:
    store = SqliteAuditStore(sqlite_conn)
    store.append(_record(id="a1", subject_analysis_id="an-1", correlation_id="corr-1"))
    store.append(_record(id="a2", subject_analysis_id="an-1", correlation_id="corr-2"))

    results = store.find(analysis_id="an-1", correlation_id="corr-2")

    assert [r["id"] for r in results] == ["a2"]
