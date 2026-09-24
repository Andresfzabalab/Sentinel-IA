"""Proves the Audit trail is append-only and queryable by analysis/correlation id."""

from __future__ import annotations

from sentinel.infrastructure.core.sqlite.audit_store import AuditRecordCreate, SqliteAuditStore


def test_append_and_query_by_analysis_id(sqlite_conn, seeded_repository_id):
    store = SqliteAuditStore(sqlite_conn)
    sqlite_conn.execute(
        "INSERT INTO analysis (id, correlation_id, trigger_mode, repository_id, policy_version_id, status, created_at) "
        "VALUES ('an-1', 'corr-1', 'mode_a', 'repo-1', 'policy-1-v1', 'completed', 't0')"
    )

    store.append(
        AuditRecordCreate(
            id="audit-1",
            actor="system",
            event_type="AnalysisCompleted",
            origin="sentinel-core",
            payload='{"verdict": "BLOCK"}',
            created_at="t0",
            subject_analysis_id="an-1",
            correlation_id="corr-1",
        )
    )

    by_analysis = store.get_by_analysis_id("an-1")
    by_correlation = store.get_by_correlation_id("corr-1")

    assert len(by_analysis) == 1
    assert by_analysis[0]["event_type"] == "AnalysisCompleted"
    assert len(by_correlation) == 1


def test_append_only_has_no_update_or_delete_method():
    """The class itself structurally offers no way to mutate a written record --
    every public method is either the one write (`append`) or a read."""
    public_methods = {name for name in dir(SqliteAuditStore) if not name.startswith("_")}
    assert public_methods == {"append", "get_by_analysis_id", "get_by_correlation_id", "find"}
