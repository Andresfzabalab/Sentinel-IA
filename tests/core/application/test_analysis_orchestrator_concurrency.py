"""Proves Phase 6's concurrency exit criterion (Implementation_Strategy.md):
the per-analysis_id serialization queue is exercised for real, concurrent
scanner completions, against the real SqliteAnalysisStore -- not a fake
store -- so a genuine race on the shared connection/in-memory Aggregate
would surface here if AnalysisWriteQueue didn't correctly serialize it.
"""

from __future__ import annotations

import itertools

from sentinel.core.application.analysis_orchestrator import AnalysisTrigger, ScannerRuntimeConfig
from sentinel.core.ports.repository_port import ChangedFileRef
from sentinel.core.ports.scanner_port import NormalizedFindingData, ScannerRunResult
from tests.core.application.conftest import seed_policy_and_repository

_ALL_FIVE_SCANNERS = ("semgrep", "bandit", "trivy", "gitleaks", "checkov")


def _sequential_id_factory(prefix: str = "an"):
    counter = itertools.count(1)
    return lambda: f"{prefix}-{next(counter)}"


def _fixed_clock(value: str = "2026-01-01T00:00:00Z"):
    return lambda: value


def test_five_concurrent_scanner_completions_are_all_recorded_without_corruption(
    build_orchestrator, fake_repository_port, fake_scanner_port, policy_store, repository_config_store, analysis_store,
):
    seed_policy_and_repository(
        policy_store, repository_config_store, enabled_scanners=_ALL_FIVE_SCANNERS,
        policy_rules={"blockOnSeverity": "critical"},
    )
    fake_repository_port.script_changed_files(
        "acme/widgets", 42,
        (
            ChangedFileRef(path="app.py", change_kind="modified"),  # semgrep, bandit
            ChangedFileRef(path="Dockerfile", change_kind="modified"),  # trivy, checkov
            ChangedFileRef(path="requirements.txt", change_kind="modified"),  # trivy
            ChangedFileRef(path="infra/main.tf", change_kind="modified"),  # checkov
            # gitleaks applies to "*", so it's selected regardless of type
        ),
    )

    # Deliberately staggered delays force real thread interleaving instead
    # of relying on scheduling luck -- the fastest and slowest scanner
    # finish in reverse registration order.
    delays = {"semgrep": 0.05, "bandit": 0.01, "trivy": 0.04, "gitleaks": 0.02, "checkov": 0.03}
    for scanner_id, delay in delays.items():
        fake_scanner_port.script_delay(scanner_id, delay)
        fake_scanner_port.script_result(
            scanner_id,
            ScannerRunResult(
                status="succeeded", exit_code=0,
                findings=(
                    NormalizedFindingData(
                        category="sast", artifact_path="app.py", artifact_type="source",
                        rule_or_check_id=f"{scanner_id}-rule", severity_level="low",
                    ),
                ),
            ),
        )

    orchestrator = build_orchestrator(
        id_factory=_sequential_id_factory(), clock=_fixed_clock(),
        scanner_runtime_config={s: ScannerRuntimeConfig(version="1.0", timeout_seconds=60) for s in _ALL_FIVE_SCANNERS},
    )

    analysis_id = orchestrator.process(
        AnalysisTrigger(
            correlation_id="corr-concurrent-1", repository_id="repo-1", trigger_mode="mode_a",
            pr_number=42, base_branch="main", head_branch="feature", author="dana", head_commit_sha="sha-1",
        )
    )

    scanner_executions = analysis_store.get_scanner_executions(analysis_id)
    assert len(scanner_executions) == 5
    assert {se["scanner_id"] for se in scanner_executions} == set(_ALL_FIVE_SCANNERS)
    assert all(se["status"] == "succeeded" for se in scanner_executions)

    findings = analysis_store.get_findings(analysis_id)
    assert len(findings) == 5  # exactly one per scanner, none lost, none duplicated
    assert {f["rule_or_check_id"] for f in findings} == {f"{s}-rule" for s in _ALL_FIVE_SCANNERS}

    row = analysis_store.get_analysis(analysis_id)
    assert row["status"] == "completed"
    assert row["verdict"] == "PASS"


def test_a_mix_of_slow_successes_and_a_timeout_still_reaches_one_correct_verdict(
    build_orchestrator, fake_repository_port, fake_scanner_port, policy_store, repository_config_store, analysis_store,
):
    seed_policy_and_repository(
        policy_store, repository_config_store, enabled_scanners=("semgrep", "bandit", "trivy"),
        policy_rules={"blockOnSeverity": "critical"},
    )
    fake_repository_port.script_changed_files(
        "acme/widgets", 42,
        (
            ChangedFileRef(path="app.py", change_kind="modified"),  # semgrep, bandit
            ChangedFileRef(path="Dockerfile", change_kind="modified"),  # trivy
        ),
    )
    fake_scanner_port.script_delay("semgrep", 0.03)
    fake_scanner_port.script_delay("bandit", 0.01)
    fake_scanner_port.script_result("trivy", ScannerRunResult(status="timed_out", failure_note="exceeded timeout"))

    orchestrator = build_orchestrator(id_factory=_sequential_id_factory(), clock=_fixed_clock())
    analysis_id = orchestrator.process(
        AnalysisTrigger(
            correlation_id="corr-concurrent-2", repository_id="repo-1", trigger_mode="mode_a",
            pr_number=42, base_branch="main", head_branch="feature", author="dana", head_commit_sha="sha-1",
        )
    )

    row = analysis_store.get_analysis(analysis_id)
    assert row["status"] == "completed"
    assert bool(row["degradation_any_scanner_failed"]) is True

    statuses = {se["scanner_id"]: se["status"] for se in analysis_store.get_scanner_executions(analysis_id)}
    assert statuses["trivy"] == "timed_out"
    assert statuses["semgrep"] == "succeeded"
    assert statuses["bandit"] == "succeeded"
