"""Proves the Analysis Aggregate's T1/T2/T3 transactions and their SQL-level
guards (Persistence_Strategy.md, Testing_Strategy.md's Persistence Tests).
"""

from __future__ import annotations

import sqlite3

import pytest

from sentinel.infrastructure.core.sqlite.analysis_store import (
    AnalysisCreate,
    AnalysisFailed,
    ArtifactCreate,
    FindingCreate,
    FindingRiskUpdate,
    ScannerExecutionCompletion,
    ScannerExecutionSeed,
    SqliteAnalysisStore,
    T3Finalize,
)
from sentinel.infrastructure.core.sqlite.exceptions import (
    ScannerExecutionNotRunning,
    VerdictAlreadySet,
)


def _analysis_create(**overrides) -> AnalysisCreate:
    defaults = dict(
        id="an-1",
        correlation_id="corr-1",
        trigger_mode="mode_a",
        repository_id="repo-1",
        policy_version_id="policy-1-v1",
        created_at="2026-01-01T00:00:00Z",
        pr_context_retrieval_status="succeeded",
        pr_number=42,
        pr_head_commit_sha="abc123",
    )
    defaults.update(overrides)
    return AnalysisCreate(**defaults)


def test_t1_creates_analysis_with_artifacts_and_scanner_executions(sqlite_conn, seeded_repository_id):
    store = SqliteAnalysisStore(sqlite_conn)

    analysis_id = store.create_analysis(
        _analysis_create(),
        artifacts=(ArtifactCreate(id="art-1", path="app.py", artifact_type="source", change_kind="modified"),),
        scanner_executions=(
            ScannerExecutionSeed(
                id="se-1", scanner_id="semgrep", scanner_version="1.70.0", timeout_seconds=120, started_at="2026-01-01T00:00:01Z"
            ),
        ),
    )

    assert analysis_id == "an-1"
    row = store.get_analysis("an-1")
    assert row["status"] == "running"
    assert row["verdict"] is None
    assert len(store.get_artifacts("an-1")) == 1
    assert len(store.get_scanner_executions("an-1")) == 1
    assert store.get_scanner_executions("an-1")[0]["status"] == "running"


def test_t1_is_idempotent_on_correlation_id(sqlite_conn, seeded_repository_id):
    """UNIQUE(correlation_id) backstop: a duplicate T1 attempt returns the
    existing analysisId instead of creating a second row (Domain_Events.md's
    Mode A idempotency rule)."""
    store = SqliteAnalysisStore(sqlite_conn)
    create = _analysis_create()

    first_id = store.create_analysis(create, artifacts=(), scanner_executions=())
    second_id = store.create_analysis(
        _analysis_create(id="an-2"),  # different id, same correlation_id -- must still collapse to the first
        artifacts=(),
        scanner_executions=(),
    )

    assert first_id == second_id == "an-1"
    count = sqlite_conn.execute("SELECT COUNT(*) AS c FROM analysis WHERE correlation_id = ?", (create.correlation_id,)).fetchone()["c"]
    assert count == 1


def test_a_genuine_integrity_error_unrelated_to_correlation_id_propagates_cleanly(sqlite_conn):
    """Regression test: an IntegrityError caused by something other than a
    duplicate correlation_id (here, a foreign key violation because no
    repository/policy_version was ever seeded) must propagate as the real
    sqlite3.IntegrityError -- not be masked by a second, failing ROLLBACK
    attempt on an already-closed transaction.
    """
    store = SqliteAnalysisStore(sqlite_conn)

    with pytest.raises(sqlite3.IntegrityError):
        store.create_analysis(_analysis_create(), artifacts=(), scanner_executions=())

    # The connection must be left usable afterwards (transaction properly closed).
    assert sqlite_conn.execute("SELECT COUNT(*) AS c FROM analysis").fetchone()["c"] == 0


def test_t1_failed_path_never_reaches_running(sqlite_conn, seeded_repository_id):
    store = SqliteAnalysisStore(sqlite_conn)

    analysis_id = store.create_failed_analysis(
        AnalysisFailed(
            id="an-failed-1",
            correlation_id="corr-failed-1",
            repository_id="repo-1",
            policy_version_id="policy-1-v1",
            failure_reason="pr_context_retrieval_failed",
            created_at="2026-01-01T00:00:00Z",
        )
    )

    row = store.get_analysis(analysis_id)
    assert row["status"] == "failed"
    assert row["failure_reason"] == "pr_context_retrieval_failed"
    assert row["verdict"] is None
    assert row["completed_at"] is not None
    assert len(store.get_artifacts(analysis_id)) == 0
    assert len(store.get_scanner_executions(analysis_id)) == 0


def test_t2_completes_scanner_execution_and_inserts_findings(sqlite_conn, seeded_repository_id):
    store = SqliteAnalysisStore(sqlite_conn)
    store.create_analysis(
        _analysis_create(),
        artifacts=(),
        scanner_executions=(
            ScannerExecutionSeed(id="se-1", scanner_id="semgrep", scanner_version="1.70.0", timeout_seconds=120, started_at="t0"),
        ),
    )

    store.complete_scanner_execution(
        ScannerExecutionCompletion(
            analysis_id="an-1",
            scanner_id="semgrep",
            status="succeeded",
            completed_at="t1",
            exit_code=0,
            findings=(
                FindingCreate(
                    id="f-1",
                    scanner_execution_id="se-1",
                    scanner_id="semgrep",
                    category="sast",
                    artifact_path="app.py",
                    artifact_type="source",
                    rule_or_check_id="python.sql-injection",
                    severity_level="high",
                ),
            ),
        )
    )

    scanner_execution = store.get_scanner_executions("an-1")[0]
    assert scanner_execution["status"] == "succeeded"
    assert scanner_execution["completed_at"] == "t1"
    findings = store.get_findings("an-1")
    assert len(findings) == 1
    assert findings[0]["rule_or_check_id"] == "python.sql-injection"


def test_t2_a_failed_or_timed_out_execution_is_never_reinterpreted_as_no_findings(sqlite_conn, seeded_repository_id):
    """P-09 / QA-03: a failed/timed-out status is recorded distinctly, not silently."""
    store = SqliteAnalysisStore(sqlite_conn)
    store.create_analysis(
        _analysis_create(),
        artifacts=(),
        scanner_executions=(
            ScannerExecutionSeed(id="se-1", scanner_id="trivy", scanner_version="0.50.0", timeout_seconds=60, started_at="t0"),
        ),
    )

    store.complete_scanner_execution(
        ScannerExecutionCompletion(
            analysis_id="an-1",
            scanner_id="trivy",
            status="timed_out",
            completed_at="t1",
            failure_note="exceeded 60s timeout",
        )
    )

    scanner_execution = store.get_scanner_executions("an-1")[0]
    assert scanner_execution["status"] == "timed_out"
    assert scanner_execution["failure_note"] == "exceeded 60s timeout"
    assert store.get_findings("an-1") == []


def test_t2_rejects_completing_an_execution_that_is_not_running(sqlite_conn, seeded_repository_id):
    store = SqliteAnalysisStore(sqlite_conn)
    store.create_analysis(
        _analysis_create(),
        artifacts=(),
        scanner_executions=(
            ScannerExecutionSeed(id="se-1", scanner_id="semgrep", scanner_version="1.70.0", timeout_seconds=120, started_at="t0"),
        ),
    )
    store.complete_scanner_execution(
        ScannerExecutionCompletion(analysis_id="an-1", scanner_id="semgrep", status="succeeded", completed_at="t1")
    )

    with pytest.raises(ScannerExecutionNotRunning):
        store.complete_scanner_execution(
            ScannerExecutionCompletion(analysis_id="an-1", scanner_id="semgrep", status="succeeded", completed_at="t2")
        )


def test_t3_sets_verdict_exactly_once(sqlite_conn, seeded_repository_id):
    store = SqliteAnalysisStore(sqlite_conn)
    store.create_analysis(
        _analysis_create(),
        artifacts=(),
        scanner_executions=(
            ScannerExecutionSeed(id="se-1", scanner_id="semgrep", scanner_version="1.70.0", timeout_seconds=120, started_at="t0"),
        ),
    )
    store.complete_scanner_execution(
        ScannerExecutionCompletion(
            analysis_id="an-1",
            scanner_id="semgrep",
            status="succeeded",
            completed_at="t1",
            findings=(
                FindingCreate(
                    id="f-1", scanner_execution_id="se-1", scanner_id="semgrep", category="sast",
                    artifact_path="app.py", artifact_type="source", rule_or_check_id="r1", severity_level="high",
                ),
            ),
        )
    )

    store.finalize_verdict(
        T3Finalize(
            analysis_id="an-1",
            security_score=42.0,
            verdict="BLOCK",
            degradation_any_scanner_failed=False,
            degradation_ai_available_at_completion=False,
            completed_at="t2",
            finding_updates=(
                FindingRiskUpdate(finding_id="f-1", correlation_group_id=None, risk_level="high", risk_heuristics_applied="[]"),
            ),
        )
    )

    row = store.get_analysis("an-1")
    assert row["status"] == "completed"
    assert row["verdict"] == "BLOCK"
    assert row["security_score"] == 42.0
    finding = store.get_findings("an-1")[0]
    assert finding["risk_level"] == "high"

    with pytest.raises(VerdictAlreadySet):
        store.finalize_verdict(
            T3Finalize(
                analysis_id="an-1",
                security_score=0.0,
                verdict="PASS",
                degradation_any_scanner_failed=False,
                degradation_ai_available_at_completion=True,
                completed_at="t3",
            )
        )

    # The write-once guard must mean the second attempt had NO effect at all.
    row_after = store.get_analysis("an-1")
    assert row_after["verdict"] == "BLOCK"
    assert row_after["security_score"] == 42.0
