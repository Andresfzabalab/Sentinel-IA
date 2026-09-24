"""Proves SqliteAnalysisStoreAdapter.load() correctly reconstructs the
domain Aggregate from storage -- the read-side needed by Crash & Restart
Recovery (Phase 6).
"""

from __future__ import annotations

from sentinel.core.domain.analysis.entities import Analysis
from sentinel.infrastructure.core.sqlite.analysis_store import (
    AnalysisCreate,
    FindingCreate,
    FindingRiskUpdate,
    ScannerExecutionCompletion,
    ScannerExecutionSeed,
    SqliteAnalysisStore,
    T3Finalize,
)
from sentinel.infrastructure.core.sqlite.analysis_store_adapter import SqliteAnalysisStoreAdapter


def test_load_reconstructs_a_completed_analysis_with_full_fidelity(sqlite_conn, seeded_repository_id):
    raw_store = SqliteAnalysisStore(sqlite_conn)
    adapter = SqliteAnalysisStoreAdapter(raw_store)

    raw_store.create_analysis(
        AnalysisCreate(
            id="an-1", correlation_id="corr-1", trigger_mode="mode_a", repository_id="repo-1",
            policy_version_id="policy-1-v1", created_at="t0", pr_context_retrieval_status="succeeded",
            pr_number=42, pr_head_branch="feature", pr_base_branch="main", pr_author="dana",
            pr_head_commit_sha="sha-1",
        ),
        artifacts=(),
        scanner_executions=(
            ScannerExecutionSeed(id="se-1", scanner_id="semgrep", scanner_version="1.70.0", timeout_seconds=120, started_at="t0"),
        ),
    )
    raw_store.complete_scanner_execution(
        ScannerExecutionCompletion(
            analysis_id="an-1", scanner_id="semgrep", status="succeeded", completed_at="t1", exit_code=0,
            findings=(
                FindingCreate(
                    id="f-1", scanner_execution_id="se-1", scanner_id="semgrep", category="sast",
                    artifact_path="app.py", artifact_type="source", rule_or_check_id="r1", severity_level="critical",
                ),
            ),
        )
    )
    raw_store.finalize_verdict(
        T3Finalize(
            analysis_id="an-1", security_score=60.0, verdict="BLOCK",
            degradation_any_scanner_failed=False, degradation_ai_available_at_completion=False,
            completed_at="t2",
            finding_updates=(
                FindingRiskUpdate(finding_id="f-1", correlation_group_id=None, risk_level="critical", risk_heuristics_applied="[]"),
            ),
        )
    )

    analysis = adapter.load("an-1")

    assert isinstance(analysis, Analysis)
    assert analysis.id == "an-1"
    assert analysis.status == "completed"
    assert analysis.verdict.value == "BLOCK"
    assert analysis.security_score.value == 60.0
    assert analysis.pr_snapshot.head_commit_sha == "sha-1"
    assert analysis.pr_snapshot.pr_number == 42
    assert len(analysis.scanner_executions) == 1
    assert analysis.scanner_executions[0].status == "succeeded"
    assert len(analysis.findings) == 1
    assert analysis.findings[0].risk.adjusted_level == "critical"


def test_load_reconstructs_a_still_running_analysis_with_no_risk_yet(sqlite_conn, seeded_repository_id):
    raw_store = SqliteAnalysisStore(sqlite_conn)
    adapter = SqliteAnalysisStoreAdapter(raw_store)

    raw_store.create_analysis(
        AnalysisCreate(
            id="an-2", correlation_id="corr-2", trigger_mode="mode_a", repository_id="repo-1",
            policy_version_id="policy-1-v1", created_at="t0",
        ),
        artifacts=(),
        scanner_executions=(
            ScannerExecutionSeed(id="se-1", scanner_id="semgrep", scanner_version="1.0", timeout_seconds=60, started_at="t0"),
        ),
    )

    analysis = adapter.load("an-2")

    assert analysis.status == "running"
    assert analysis.verdict is None
    assert analysis.security_score is None
    assert analysis.scanner_executions[0].status == "running"


def test_load_raises_key_error_for_an_unknown_analysis_id(sqlite_conn):
    adapter = SqliteAnalysisStoreAdapter(SqliteAnalysisStore(sqlite_conn))

    import pytest

    with pytest.raises(KeyError):
        adapter.load("does-not-exist")


def test_recover_stale_scanner_executions_marks_running_rows_failed(sqlite_conn, seeded_repository_id):
    raw_store = SqliteAnalysisStore(sqlite_conn)
    adapter = SqliteAnalysisStoreAdapter(raw_store)

    raw_store.create_analysis(
        AnalysisCreate(
            id="an-3", correlation_id="corr-3", trigger_mode="mode_a", repository_id="repo-1",
            policy_version_id="policy-1-v1", created_at="t0",
        ),
        artifacts=(),
        scanner_executions=(
            ScannerExecutionSeed(id="se-1", scanner_id="semgrep", scanner_version="1.0", timeout_seconds=60, started_at="t0"),
            ScannerExecutionSeed(id="se-2", scanner_id="bandit", scanner_version="1.0", timeout_seconds=60, started_at="t0"),
        ),
    )

    affected = adapter.recover_stale_scanner_executions("process restarted mid-execution", "t1")

    assert affected == ("an-3",)
    statuses = {se["scanner_id"]: se["status"] for se in raw_store.get_scanner_executions("an-3")}
    assert statuses == {"semgrep": "failed", "bandit": "failed"}


def test_find_running_analysis_ids(sqlite_conn, seeded_repository_id):
    raw_store = SqliteAnalysisStore(sqlite_conn)
    adapter = SqliteAnalysisStoreAdapter(raw_store)

    raw_store.create_analysis(
        AnalysisCreate(
            id="an-4", correlation_id="corr-4", trigger_mode="mode_a", repository_id="repo-1",
            policy_version_id="policy-1-v1", created_at="t0",
        ),
        artifacts=(), scanner_executions=(),
    )

    assert adapter.find_running_analysis_ids() == ("an-4",)
