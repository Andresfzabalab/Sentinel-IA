"""Proves Phase 3's exit criteria (Implementation_Strategy.md): a full,
real database-backed Analysis runs from a fake PullRequestReceived trigger
through to a persisted verdict -- including the idempotency path and the
T1-Failed path -- against Fake RepositoryPort/ScannerPort.
"""

from __future__ import annotations

import itertools
import logging

from sentinel.core.application.analysis_orchestrator import AnalysisTrigger, ScannerRuntimeConfig
from sentinel.core.domain.services.artifact_classification import ChangedFile
from sentinel.core.ports.repository_port import ChangedFileRef
from sentinel.core.ports.scanner_port import NormalizedFindingData, ScannerRunResult
from tests.core.application.conftest import seed_policy_and_repository


def _sequential_id_factory(prefix: str = "an"):
    counter = itertools.count(1)
    return lambda: f"{prefix}-{next(counter)}"


def _fixed_clock(value: str = "2026-01-01T00:00:00Z"):
    return lambda: value


class _CollectingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _mode_a_trigger(correlation_id: str = "corr-1", pr_number: int = 42, head_commit_sha: str = "sha-1") -> AnalysisTrigger:
    return AnalysisTrigger(
        correlation_id=correlation_id,
        repository_id="repo-1",
        trigger_mode="mode_a",
        pr_number=pr_number,
        base_branch="main",
        head_branch="feature",
        author="dana",
        head_commit_sha=head_commit_sha,
    )


def test_full_pipeline_produces_a_persisted_pass_verdict(
    build_orchestrator, fake_repository_port, fake_scanner_port, policy_store, repository_config_store, analysis_store,
):
    seed_policy_and_repository(policy_store, repository_config_store, policy_rules={"blockOnSeverity": "critical"})
    fake_repository_port.script_changed_files(
        "acme/widgets", 42, (ChangedFileRef(path="app.py", change_kind="modified"),)
    )
    fake_scanner_port.script_result(
        "semgrep",
        ScannerRunResult(
            status="succeeded", exit_code=0,
            findings=(
                NormalizedFindingData(
                    category="sast", artifact_path="app.py", artifact_type="source",
                    rule_or_check_id="python.safe", severity_level="low",
                ),
            ),
        ),
    )

    orchestrator = build_orchestrator(
        id_factory=_sequential_id_factory(), clock=_fixed_clock(),
        scanner_runtime_config={"semgrep": ScannerRuntimeConfig(version="1.70.0", timeout_seconds=120)},
    )

    analysis_id = orchestrator.process(_mode_a_trigger())

    row = analysis_store.get_analysis(analysis_id)
    assert row["status"] == "completed"
    assert row["verdict"] == "PASS"
    assert len(analysis_store.get_findings(analysis_id)) == 1
    assert len(fake_repository_port.published_results) == 1
    assert fake_repository_port.published_results[0].result.verdict == "PASS"


def test_t2_commit_is_logged_with_its_own_scanner_execution_id(
    build_orchestrator, fake_repository_port, fake_scanner_port, policy_store, repository_config_store, analysis_store,
):
    """Observability_and_Logging.md: `scannerExecutionId` is present only
    on lines specific to one Scanner Execution -- this proves the T2
    commit log line carries it, alongside the same `correlationId`/
    `analysisId` every other stage of this Analysis carries.
    """
    seed_policy_and_repository(policy_store, repository_config_store, policy_rules={"blockOnSeverity": "critical"})
    fake_repository_port.script_changed_files(
        "acme/widgets", 42, (ChangedFileRef(path="app.py", change_kind="modified"),)
    )
    fake_scanner_port.script_result("semgrep", ScannerRunResult(status="succeeded", exit_code=0))

    orchestrator = build_orchestrator(
        id_factory=_sequential_id_factory(), clock=_fixed_clock(),
        scanner_runtime_config={"semgrep": ScannerRuntimeConfig(version="1.70.0", timeout_seconds=120)},
    )

    root = logging.getLogger()
    collector = _CollectingHandler()
    previous_level = root.level
    root.addHandler(collector)
    root.setLevel(logging.INFO)
    try:
        analysis_id = orchestrator.process(_mode_a_trigger())
    finally:
        root.removeHandler(collector)
        root.setLevel(previous_level)

    t2_records = [r for r in collector.records if getattr(r, "event", None) == "t2_committed"]
    semgrep_record = next(r for r in t2_records if r.scanner_execution_id == f"{analysis_id}-se-semgrep")
    assert semgrep_record.analysis_id == analysis_id
    assert semgrep_record.correlation_id == "corr-1"
    assert semgrep_record.levelname == "INFO"  # succeeded -- not a degradation


def test_t2_commit_for_a_failed_scanner_is_logged_at_warning(
    build_orchestrator, fake_repository_port, fake_scanner_port, policy_store, repository_config_store,
):
    seed_policy_and_repository(policy_store, repository_config_store, policy_rules={"blockOnSeverity": "critical"})
    fake_repository_port.script_changed_files(
        "acme/widgets", 42, (ChangedFileRef(path="app.py", change_kind="modified"),)
    )
    fake_scanner_port.script_result("semgrep", ScannerRunResult(status="failed", exit_code=1, failure_note="crashed"))
    fake_scanner_port.script_result("gitleaks", ScannerRunResult(status="succeeded", exit_code=0))

    orchestrator = build_orchestrator(
        id_factory=_sequential_id_factory(), clock=_fixed_clock(),
        scanner_runtime_config={"semgrep": ScannerRuntimeConfig(version="1.70.0", timeout_seconds=120)},
    )

    root = logging.getLogger()
    collector = _CollectingHandler()
    previous_level = root.level
    root.addHandler(collector)
    root.setLevel(logging.INFO)
    try:
        analysis_id = orchestrator.process(_mode_a_trigger())
    finally:
        root.removeHandler(collector)
        root.setLevel(previous_level)

    t2_records = [r for r in collector.records if getattr(r, "event", None) == "t2_committed"]
    semgrep_record = next(r for r in t2_records if r.scanner_execution_id == f"{analysis_id}-se-semgrep")
    gitleaks_record = next(r for r in t2_records if r.scanner_execution_id == f"{analysis_id}-se-gitleaks")
    assert semgrep_record.levelname == "WARNING"  # a scanner failure is expected-but-notable degradation
    assert gitleaks_record.levelname == "INFO"  # succeeded -- unaffected by the other scanner's failure


def test_full_pipeline_blocks_on_a_critical_finding(
    build_orchestrator, fake_repository_port, fake_scanner_port, policy_store, repository_config_store, analysis_store,
):
    seed_policy_and_repository(policy_store, repository_config_store, policy_rules={"blockOnSeverity": "critical"})
    fake_repository_port.script_changed_files(
        "acme/widgets", 42, (ChangedFileRef(path="app.py", change_kind="modified"),)
    )
    fake_scanner_port.script_result(
        "semgrep",
        ScannerRunResult(
            status="succeeded", exit_code=0,
            findings=(
                NormalizedFindingData(
                    category="sast", artifact_path="app.py", artifact_type="source",
                    rule_or_check_id="python.sql-injection", severity_level="critical",
                ),
            ),
        ),
    )

    orchestrator = build_orchestrator(id_factory=_sequential_id_factory(), clock=_fixed_clock())
    analysis_id = orchestrator.process(_mode_a_trigger())

    row = analysis_store.get_analysis(analysis_id)
    assert row["verdict"] == "BLOCK"
    finding = analysis_store.get_findings(analysis_id)[0]
    assert finding["risk_level"] == "critical"
    assert fake_repository_port.published_results[0].result.verdict == "BLOCK"


def test_repeated_correlation_id_returns_the_same_analysis_id_without_rescanning(
    build_orchestrator, fake_repository_port, fake_scanner_port, policy_store, repository_config_store,
):
    """The direct proof of Domain_Events.md's Mode A idempotency rule."""
    seed_policy_and_repository(policy_store, repository_config_store, enabled_scanners=("semgrep",))
    fake_repository_port.script_changed_files(
        "acme/widgets", 42, (ChangedFileRef(path="app.py", change_kind="modified"),)
    )

    orchestrator = build_orchestrator(id_factory=_sequential_id_factory(), clock=_fixed_clock())

    first_id = orchestrator.process(_mode_a_trigger(correlation_id="corr-dup"))
    second_id = orchestrator.process(_mode_a_trigger(correlation_id="corr-dup"))

    assert first_id == second_id
    # No re-scan on the duplicate delivery: the scanner ran exactly once,
    # for the original trigger only.
    assert len(fake_scanner_port.calls) == 1

    orchestrator.process(_mode_a_trigger(correlation_id="corr-dup"))
    assert len(fake_scanner_port.calls) == 1


def test_a_different_correlation_id_produces_a_genuinely_new_analysis(
    build_orchestrator, fake_repository_port, policy_store, repository_config_store,
):
    seed_policy_and_repository(policy_store, repository_config_store)
    fake_repository_port.script_changed_files("acme/widgets", 42, ())

    orchestrator = build_orchestrator(id_factory=_sequential_id_factory(), clock=_fixed_clock())

    first_id = orchestrator.process(_mode_a_trigger(correlation_id="corr-a", head_commit_sha="sha-1"))
    second_id = orchestrator.process(_mode_a_trigger(correlation_id="corr-b", head_commit_sha="sha-2"))

    assert first_id != second_id


def test_t1_failed_path_never_hangs_and_produces_no_verdict(
    build_orchestrator, fake_repository_port, policy_store, repository_config_store, analysis_store, audit_store,
):
    """A fake RepositoryPort configured to fail produces a failed Analysis,
    never a hang, and never a fabricated verdict."""
    seed_policy_and_repository(policy_store, repository_config_store)
    fake_repository_port.script_failure("acme/widgets", 42)

    orchestrator = build_orchestrator(id_factory=_sequential_id_factory(), clock=_fixed_clock())
    analysis_id = orchestrator.process(_mode_a_trigger())

    row = analysis_store.get_analysis(analysis_id)
    assert row["status"] == "failed"
    assert row["failure_reason"] == "pr_context_retrieval_failed"
    assert row["verdict"] is None
    assert row["completed_at"] is not None  # terminal immediately, never left "running"
    assert analysis_store.get_scanner_executions(analysis_id) == []
    assert analysis_store.get_findings(analysis_id) == []

    # GitHub still gets a signal: the ERROR status, using the commit sha
    # known from the webhook payload itself (never a fabricated status).
    assert len(fake_repository_port.published_results) == 1
    assert fake_repository_port.published_results[0].result.verdict == "ERROR"
    assert fake_repository_port.published_results[0].head_commit_sha == "sha-1"

    audit_records = audit_store.get_by_analysis_id(analysis_id)
    assert any(r["event_type"] == "AnalysisFailed" for r in audit_records)


def test_t1_failed_analysis_is_also_idempotent_on_correlation_id(
    build_orchestrator, fake_repository_port, policy_store, repository_config_store,
):
    seed_policy_and_repository(policy_store, repository_config_store)
    fake_repository_port.script_failure("acme/widgets", 42)

    orchestrator = build_orchestrator(id_factory=_sequential_id_factory(), clock=_fixed_clock())
    first_id = orchestrator.process(_mode_a_trigger(correlation_id="corr-fail-dup"))
    second_id = orchestrator.process(_mode_a_trigger(correlation_id="corr-fail-dup"))

    assert first_id == second_id


def test_mode_b_never_calls_repository_port_and_never_posts_a_github_status(
    build_orchestrator, fake_repository_port, fake_scanner_port, policy_store, repository_config_store, analysis_store,
):
    seed_policy_and_repository(policy_store, repository_config_store)

    orchestrator = build_orchestrator(id_factory=_sequential_id_factory(), clock=_fixed_clock())
    trigger = AnalysisTrigger(
        correlation_id="corr-modeb-1",
        repository_id="repo-1",
        trigger_mode="mode_b",
        manual_trigger_key="devsecops-retry-1",
        changed_files=(ChangedFile(path="app.py", change_kind="modified"),),
    )

    analysis_id = orchestrator.process(trigger)

    row = analysis_store.get_analysis(analysis_id)
    assert row["status"] == "completed"
    assert row["trigger_mode"] == "mode_b"
    assert row["pr_number"] is None
    assert fake_repository_port.published_results == []  # no PR, no commit -- nothing to post


def test_a_scanner_failure_degrades_but_still_reaches_a_verdict(
    build_orchestrator, fake_repository_port, fake_scanner_port, policy_store, repository_config_store, analysis_store,
):
    """P-09 / QA-03, exercised end-to-end through the Orchestrator."""
    seed_policy_and_repository(policy_store, repository_config_store, enabled_scanners=("semgrep", "gitleaks"))
    fake_repository_port.script_changed_files(
        "acme/widgets", 42, (ChangedFileRef(path="app.py", change_kind="modified"),)
    )
    fake_scanner_port.script_result("semgrep", ScannerRunResult(status="timed_out", failure_note="exceeded timeout"))

    orchestrator = build_orchestrator(id_factory=_sequential_id_factory(), clock=_fixed_clock())
    analysis_id = orchestrator.process(_mode_a_trigger())

    row = analysis_store.get_analysis(analysis_id)
    assert row["status"] == "completed"
    assert row["verdict"] in ("PASS", "BLOCK")
    assert bool(row["degradation_any_scanner_failed"]) is True
    scanner_executions = {se["scanner_id"]: se["status"] for se in analysis_store.get_scanner_executions(analysis_id)}
    assert scanner_executions["semgrep"] == "timed_out"


def test_verdict_is_identical_regardless_of_which_scanner_port_instance_is_used(
    build_orchestrator, fake_repository_port, fake_scanner_port, policy_store, repository_config_store, analysis_store,
):
    """A light QA-02-style determinism check at the orchestration level:
    same findings in, same verdict out."""
    seed_policy_and_repository(policy_store, repository_config_store, policy_rules={"blockOnSeverity": "high"})
    fake_repository_port.script_changed_files(
        "acme/widgets", 42, (ChangedFileRef(path="app.py", change_kind="modified"),)
    )
    fake_repository_port.script_changed_files(
        "acme/widgets", 43, (ChangedFileRef(path="app.py", change_kind="modified"),)
    )
    finding = NormalizedFindingData(
        category="sast", artifact_path="app.py", artifact_type="source", rule_or_check_id="r1", severity_level="high"
    )
    fake_scanner_port.script_result("semgrep", ScannerRunResult(status="succeeded", exit_code=0, findings=(finding,)))

    orchestrator = build_orchestrator(id_factory=_sequential_id_factory(), clock=_fixed_clock())

    first_id = orchestrator.process(_mode_a_trigger(correlation_id="corr-x", pr_number=42, head_commit_sha="sha-1"))
    second_id = orchestrator.process(_mode_a_trigger(correlation_id="corr-y", pr_number=43, head_commit_sha="sha-2"))

    first_row = analysis_store.get_analysis(first_id)
    second_row = analysis_store.get_analysis(second_id)
    assert first_row["verdict"] == second_row["verdict"] == "BLOCK"
    assert first_row["security_score"] == second_row["security_score"]
