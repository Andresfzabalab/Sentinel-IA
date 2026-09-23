"""Proves the Analysis Aggregate's invariants (Entities_Value_Objects.md's
Invariant Summary table) fully offline -- no I/O, no fakes needed (QA-05).
"""

from __future__ import annotations

import pytest

from sentinel.core.domain.analysis.entities import Analysis, Finding, ScannerExecution
from sentinel.core.domain.analysis.value_objects import Risk, SecurityScore, Severity, Verdict
from sentinel.core.domain.exceptions import (
    FindingsFrozen,
    MissingRiskAssessment,
    ScannerExecutionAlreadyTerminal,
    VerdictAlreadySet,
)


def _running_analysis(scanner_id: str = "semgrep") -> Analysis:
    return Analysis.start(
        id="an-1",
        correlation_id="corr-1",
        trigger_mode="mode_a",
        repository_id="repo-1",
        policy_version_id="pv-1",
        artifacts=(),
        scanner_executions=[
            ScannerExecution(id="se-1", scanner_id=scanner_id, scanner_version="1.0", timeout_seconds=60, started_at="t0")
        ],
        created_at="t0",
    )


def _finding(id: str = "f-1", severity_level: str = "high") -> Finding:
    return Finding(
        id=id,
        scanner_execution_id="se-1",
        scanner_id="semgrep",
        category="sast",
        artifact_path="app.py",
        artifact_type="source",
        rule_or_check_id="r1",
        severity=Severity(level=severity_level),
    )


class TestScannerExecution:
    def test_completes_to_a_terminal_status(self) -> None:
        execution = ScannerExecution(id="se-1", scanner_id="semgrep", scanner_version="1.0", timeout_seconds=60, started_at="t0")

        execution.complete("succeeded", completed_at="t1", exit_code=0)

        assert execution.status == "succeeded"
        assert execution.is_terminal is True

    def test_a_timed_out_execution_is_terminal_and_distinguishable_from_succeeded(self) -> None:
        execution = ScannerExecution(id="se-1", scanner_id="trivy", scanner_version="1.0", timeout_seconds=60, started_at="t0")

        execution.complete("timed_out", completed_at="t1", failure_note="exceeded timeout")

        assert execution.status == "timed_out"
        assert execution.status != "succeeded"
        assert execution.is_terminal is True

    def test_cannot_complete_an_already_terminal_execution(self) -> None:
        execution = ScannerExecution(id="se-1", scanner_id="semgrep", scanner_version="1.0", timeout_seconds=60, started_at="t0")
        execution.complete("succeeded", completed_at="t1")

        with pytest.raises(ScannerExecutionAlreadyTerminal):
            execution.complete("failed", completed_at="t2")


class TestAnalysisScanningPhase:
    def test_complete_scanner_execution_appends_findings(self) -> None:
        analysis = _running_analysis()

        analysis.complete_scanner_execution("semgrep", "succeeded", completed_at="t1", findings=(_finding(),))

        assert len(analysis.findings) == 1
        assert analysis.find_scanner_execution("semgrep").status == "succeeded"

    def test_all_scanner_executions_terminal_reflects_remaining_running_executions(self) -> None:
        analysis = Analysis.start(
            id="an-1", correlation_id="c1", trigger_mode="mode_a", repository_id="r1", policy_version_id="pv1",
            artifacts=(), created_at="t0",
            scanner_executions=[
                ScannerExecution(id="se-1", scanner_id="semgrep", scanner_version="1.0", timeout_seconds=60, started_at="t0"),
                ScannerExecution(id="se-2", scanner_id="trivy", scanner_version="1.0", timeout_seconds=60, started_at="t0"),
            ],
        )
        assert analysis.all_scanner_executions_terminal is False

        analysis.complete_scanner_execution("semgrep", "succeeded", completed_at="t1")
        assert analysis.all_scanner_executions_terminal is False

        analysis.complete_scanner_execution("trivy", "failed", completed_at="t1", failure_note="crashed")
        assert analysis.all_scanner_executions_terminal is True

    def test_cannot_add_findings_once_analysis_is_completed(self) -> None:
        analysis = _running_analysis()
        analysis.complete_scanner_execution("semgrep", "succeeded", completed_at="t1", findings=(_finding(),))
        analysis.findings[0].assign_risk(Risk(adjusted_level="high"))
        analysis.record_verdict(
            Verdict(value="PASS", policy_version_id="pv-1"),
            SecurityScore(value=100.0),
            degradation_any_scanner_failed=False,
            degradation_ai_available_at_completion=True,
            completed_at="t2",
        )

        with pytest.raises(FindingsFrozen):
            analysis.complete_scanner_execution("semgrep", "succeeded", completed_at="t3")


class TestAnalysisCorrelation:
    def test_findings_sharing_the_same_location_are_grouped(self) -> None:
        analysis = _running_analysis()
        f1 = _finding(id="f-1")
        f1.location_file = "app.py"
        f1.location_line_start = 10
        f2 = Finding(
            id="f-2", scanner_execution_id="se-1", scanner_id="bandit", category="sast",
            artifact_path="app.py", artifact_type="source", rule_or_check_id="r2",
            severity=Severity(level="medium"), location_file="app.py", location_line_start=10,
        )
        analysis.complete_scanner_execution("semgrep", "succeeded", completed_at="t1", findings=(f1, f2))

        analysis.correlate_findings()

        assert f1.correlation_group_id is not None
        assert f1.correlation_group_id == f2.correlation_group_id

    def test_a_singleton_finding_is_left_uncorrelated(self) -> None:
        analysis = _running_analysis()
        analysis.complete_scanner_execution("semgrep", "succeeded", completed_at="t1", findings=(_finding(),))

        analysis.correlate_findings()

        assert analysis.findings[0].correlation_group_id is None

    def test_correlation_is_deterministic(self) -> None:
        analysis = _running_analysis()
        f1 = Finding(
            id="f-1", scanner_execution_id="se-1", scanner_id="semgrep", category="sast",
            artifact_path="app.py", artifact_type="source", rule_or_check_id="r1", severity=Severity(level="high"),
            location_file="app.py", location_line_start=5,
        )
        f2 = Finding(
            id="f-2", scanner_execution_id="se-1", scanner_id="bandit", category="sast",
            artifact_path="app.py", artifact_type="source", rule_or_check_id="r2", severity=Severity(level="medium"),
            location_file="app.py", location_line_start=5,
        )
        analysis.complete_scanner_execution("semgrep", "succeeded", completed_at="t1", findings=(f1, f2))

        analysis.correlate_findings()
        first_group = f1.correlation_group_id
        f1.assign_correlation_group(None)
        f2.assign_correlation_group(None)
        analysis.correlate_findings()

        assert f1.correlation_group_id == first_group

    def test_correlation_group_sizes_reflects_group_membership(self) -> None:
        analysis = _running_analysis()
        f1 = Finding(
            id="f-1", scanner_execution_id="se-1", scanner_id="semgrep", category="sast",
            artifact_path="app.py", artifact_type="source", rule_or_check_id="r1", severity=Severity(level="high"),
            location_file="app.py", location_line_start=5,
        )
        f2 = Finding(
            id="f-2", scanner_execution_id="se-1", scanner_id="bandit", category="sast",
            artifact_path="app.py", artifact_type="source", rule_or_check_id="r2", severity=Severity(level="medium"),
            location_file="app.py", location_line_start=5,
        )
        f3 = _finding(id="f-3")  # unrelated, no location
        analysis.complete_scanner_execution("semgrep", "succeeded", completed_at="t1", findings=(f1, f2, f3))

        analysis.correlate_findings()
        sizes = analysis.correlation_group_sizes()

        assert sizes["f-1"] == 2
        assert sizes["f-2"] == 2
        assert sizes["f-3"] == 1


class TestAnalysisVerdict:
    def test_record_verdict_requires_every_finding_to_have_risk_assigned(self) -> None:
        analysis = _running_analysis()
        analysis.complete_scanner_execution("semgrep", "succeeded", completed_at="t1", findings=(_finding(),))
        # deliberately not calling assign_risk()

        with pytest.raises(MissingRiskAssessment):
            analysis.record_verdict(
                Verdict(value="PASS", policy_version_id="pv-1"),
                SecurityScore(value=100.0),
                degradation_any_scanner_failed=False,
                degradation_ai_available_at_completion=True,
                completed_at="t2",
            )

    def test_verdict_is_set_exactly_once(self) -> None:
        """The single most important invariant in the whole domain (P-02, P-04)."""
        analysis = _running_analysis()
        analysis.complete_scanner_execution("semgrep", "succeeded", completed_at="t1", findings=(_finding(),))
        analysis.findings[0].assign_risk(Risk(adjusted_level="high"))

        analysis.record_verdict(
            Verdict(value="BLOCK", policy_version_id="pv-1", triggered_rules=("blockOnSeverity>=high",)),
            SecurityScore(value=80.0),
            degradation_any_scanner_failed=False,
            degradation_ai_available_at_completion=True,
            completed_at="t2",
        )

        assert analysis.status == "completed"
        assert analysis.verdict.value == "BLOCK"

        with pytest.raises(VerdictAlreadySet):
            analysis.record_verdict(
                Verdict(value="PASS", policy_version_id="pv-1"),
                SecurityScore(value=100.0),
                degradation_any_scanner_failed=False,
                degradation_ai_available_at_completion=True,
                completed_at="t3",
            )

        # The rejected second attempt must not have changed anything.
        assert analysis.verdict.value == "BLOCK"
        assert analysis.security_score.value == 80.0

    def test_verdict_is_none_until_record_verdict_is_called(self) -> None:
        analysis = _running_analysis()
        assert analysis.verdict is None

    def test_verdict_value_object_is_immutable_once_constructed(self) -> None:
        """Structural proof of P-02/P-04: even holding a Verdict instance,
        no code path can mutate its value -- it is a frozen dataclass."""
        import dataclasses

        verdict = Verdict(value="BLOCK", policy_version_id="pv-1")
        with pytest.raises(dataclasses.FrozenInstanceError):
            verdict.value = "PASS"


class TestAnalysisFailedPath:
    def test_create_failed_never_passes_through_running(self) -> None:
        analysis = Analysis.create_failed(
            id="an-failed",
            correlation_id="corr-failed",
            repository_id="repo-1",
            policy_version_id="pv-1",
            failure_reason="pr_context_retrieval_failed",
            created_at="t0",
        )

        assert analysis.status == "failed"
        assert analysis.verdict is None
        assert analysis.completed_at == "t0"
        assert analysis.findings == []
        assert analysis.scanner_executions == []
