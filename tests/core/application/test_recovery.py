"""Proves Phase 6's Crash & Restart Recovery exit criterion
(Implementation_Strategy.md, Persistence_Strategy.md): a scanner_execution
left 'running' by a killed process becomes 'failed' on the next startup,
and its owning Analysis -- if now fully terminal -- proceeds through
finalization to a real verdict, never a second hang.
"""

from __future__ import annotations

import itertools

from sentinel.infrastructure.core.sqlite.analysis_store import (
    AnalysisCreate,
    FindingCreate,
    ScannerExecutionCompletion,
    ScannerExecutionSeed,
)
from tests.core.application.conftest import seed_policy_and_repository


def _sequential_id_factory(prefix: str = "an"):
    counter = itertools.count(1)
    return lambda: f"{prefix}-{next(counter)}"


def _fixed_clock(value: str = "2026-01-01T00:00:00Z"):
    return lambda: value


def _simulate_crash_mid_analysis(analysis_store, *, repository_id: str, policy_version_id: str) -> str:
    """Directly seeds the DB to look exactly like a process that died
    between two scanners' completions: one scanner already 'succeeded'
    with a finding, the other still 'running' -- never resolved.
    """
    analysis_id = "an-crashed-1"
    analysis_store.create_analysis(
        AnalysisCreate(
            id=analysis_id, correlation_id="corr-crashed-1", trigger_mode="mode_a",
            repository_id=repository_id, policy_version_id=policy_version_id, created_at="t0",
            pr_context_retrieval_status="succeeded", pr_number=42, pr_head_branch="feature",
            pr_base_branch="main", pr_author="dana", pr_head_commit_sha="sha-1",
        ),
        artifacts=(),
        scanner_executions=(
            ScannerExecutionSeed(id="se-semgrep", scanner_id="semgrep", scanner_version="1.0", timeout_seconds=60, started_at="t0"),
            ScannerExecutionSeed(id="se-bandit", scanner_id="bandit", scanner_version="1.0", timeout_seconds=60, started_at="t0"),
        ),
    )
    analysis_store.complete_scanner_execution(
        ScannerExecutionCompletion(
            analysis_id=analysis_id, scanner_id="semgrep", status="succeeded", completed_at="t1", exit_code=0,
            findings=(
                FindingCreate(
                    id="f-1", scanner_execution_id="se-semgrep", scanner_id="semgrep", category="sast",
                    artifact_path="app.py", artifact_type="source", rule_or_check_id="r1", severity_level="high",
                ),
            ),
        )
    )
    # 'bandit' is deliberately left 'running' -- this is the simulated crash.
    return analysis_id


def test_recovery_marks_stale_executions_failed_and_finalizes_the_analysis(
    build_orchestrator, policy_store, repository_config_store, analysis_store, audit_store, fake_repository_port,
):
    seed_policy_and_repository(policy_store, repository_config_store, policy_rules={"blockOnSeverity": "critical"})
    analysis_id = _simulate_crash_mid_analysis(analysis_store, repository_id="repo-1", policy_version_id="policy-1-v1")

    # Pre-conditions: exactly what a crash mid-Analysis looks like.
    pre_row = analysis_store.get_analysis(analysis_id)
    assert pre_row["status"] == "running"
    pre_statuses = {se["scanner_id"]: se["status"] for se in analysis_store.get_scanner_executions(analysis_id)}
    assert pre_statuses == {"semgrep": "succeeded", "bandit": "running"}

    orchestrator = build_orchestrator(id_factory=_sequential_id_factory(), clock=_fixed_clock())
    orchestrator.recover_incomplete_analyses()

    post_statuses = {se["scanner_id"]: se["status"] for se in analysis_store.get_scanner_executions(analysis_id)}
    assert post_statuses["bandit"] == "failed"
    bandit_row = next(se for se in analysis_store.get_scanner_executions(analysis_id) if se["scanner_id"] == "bandit")
    assert bandit_row["failure_note"] == "process restarted mid-execution"
    assert post_statuses["semgrep"] == "succeeded"  # untouched -- it had already finished cleanly

    post_row = analysis_store.get_analysis(analysis_id)
    assert post_row["status"] == "completed"
    assert post_row["verdict"] in ("PASS", "BLOCK")
    assert bool(post_row["degradation_any_scanner_failed"]) is True

    # The pre-crash finding survived and was risk-assessed as part of recovery.
    finding = analysis_store.get_findings(analysis_id)[0]
    assert finding["risk_level"] is not None

    # The mandatory channel still gets a (late) status, even after recovery.
    assert len(fake_repository_port.published_results) == 1


def test_recovery_records_the_completion_in_the_audit_trail(
    build_orchestrator, policy_store, repository_config_store, analysis_store, audit_store,
):
    seed_policy_and_repository(policy_store, repository_config_store)
    analysis_id = _simulate_crash_mid_analysis(analysis_store, repository_id="repo-1", policy_version_id="policy-1-v1")

    orchestrator = build_orchestrator(id_factory=_sequential_id_factory(), clock=_fixed_clock())
    orchestrator.recover_incomplete_analyses()

    audit_records = audit_store.get_by_analysis_id(analysis_id)
    assert any(r["event_type"] == "AnalysisCompleted" for r in audit_records)


def test_recovery_with_nothing_stale_is_a_safe_noop(build_orchestrator, policy_store, repository_config_store):
    seed_policy_and_repository(policy_store, repository_config_store)

    orchestrator = build_orchestrator(id_factory=_sequential_id_factory(), clock=_fixed_clock())

    orchestrator.recover_incomplete_analyses()  # must not raise with an empty database


def test_recovery_never_touches_an_already_completed_analysis(
    build_orchestrator, fake_repository_port, fake_scanner_port, policy_store, repository_config_store, analysis_store,
):
    from sentinel.core.application.analysis_orchestrator import AnalysisTrigger
    from sentinel.core.ports.repository_port import ChangedFileRef

    seed_policy_and_repository(policy_store, repository_config_store)
    fake_repository_port.script_changed_files("acme/widgets", 42, (ChangedFileRef(path="app.py", change_kind="modified"),))

    orchestrator = build_orchestrator(id_factory=_sequential_id_factory(), clock=_fixed_clock())
    analysis_id = orchestrator.process(
        AnalysisTrigger(
            correlation_id="corr-already-done", repository_id="repo-1", trigger_mode="mode_a",
            pr_number=42, base_branch="main", head_branch="feature", author="dana", head_commit_sha="sha-1",
        )
    )
    row_before = analysis_store.get_analysis(analysis_id)

    orchestrator.recover_incomplete_analyses()

    row_after = analysis_store.get_analysis(analysis_id)
    assert row_after["verdict"] == row_before["verdict"]
    assert row_after["completed_at"] == row_before["completed_at"]
