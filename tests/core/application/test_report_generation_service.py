"""Proves the Phase 8 Report Generation Service: redaction for the
developer audience, and the 409-mapped "not complete yet" error."""

from __future__ import annotations

import pytest

from sentinel.core.application.report_generation_service import (
    AnalysisNotCompleteError,
    generate_report,
)
from sentinel.core.domain.analysis.entities import Analysis, Finding, ScannerExecution
from sentinel.core.domain.analysis.value_objects import Risk, SecurityScore, Severity, Verdict


def _completed_analysis_with_a_secret_finding() -> Analysis:
    analysis = Analysis.start(
        id="an-1", correlation_id="corr-1", trigger_mode="mode_a", repository_id="repo-1",
        policy_version_id="pv-1", artifacts=(), created_at="t0",
        scanner_executions=[ScannerExecution(id="se-1", scanner_id="gitleaks", scanner_version="8.0", timeout_seconds=60, started_at="t0")],
    )
    secret_finding = Finding(
        id="f-1", scanner_execution_id="se-1", scanner_id="gitleaks", category="secret",
        artifact_path="config.py", artifact_type="other", rule_or_check_id="aws-key",
        severity=Severity(level="critical"), secret_value_redaction_flag=True,
    )
    ordinary_finding = Finding(
        id="f-2", scanner_execution_id="se-1", scanner_id="semgrep", category="sast",
        artifact_path="app.py", artifact_type="source", rule_or_check_id="r1",
        severity=Severity(level="high"),
    )
    analysis.complete_scanner_execution("gitleaks", "succeeded", "t1", findings=(secret_finding, ordinary_finding))
    for finding in analysis.findings:
        finding.assign_risk(Risk(adjusted_level=finding.severity.level))
    analysis.record_verdict(
        Verdict(value="BLOCK", policy_version_id="pv-1", triggered_rules=("r1",)),
        SecurityScore(value=40.0),
        degradation_any_scanner_failed=False, degradation_ai_available_at_completion=False,
        completed_at="t2",
    )
    return analysis


def test_devsecops_report_includes_every_finding() -> None:
    analysis = _completed_analysis_with_a_secret_finding()

    report = generate_report(analysis, "devsecops", generated_at="t3")

    assert len(report.content["findings"]) == 2
    assert report.content["verdict"] == "BLOCK"
    assert report.content["triggeredRules"] == ["r1"]


def test_developer_report_excludes_secret_flagged_findings() -> None:
    analysis = _completed_analysis_with_a_secret_finding()

    report = generate_report(analysis, "developer", generated_at="t3")

    assert len(report.content["findings"]) == 1
    assert report.content["findings"][0]["ruleOrCheckId"] == "r1"
    assert report.content["triggeredRules"] == []  # rule detail withheld from developer view


def test_ai_section_is_always_pending_before_phase_9() -> None:
    analysis = _completed_analysis_with_a_secret_finding()

    report = generate_report(analysis, "devsecops", generated_at="t3")

    assert report.ai_section == {"status": "pending", "contentRef": None}


def test_requesting_a_report_for_an_incomplete_analysis_raises() -> None:
    analysis = Analysis.start(
        id="an-2", correlation_id="corr-2", trigger_mode="mode_a", repository_id="repo-1",
        policy_version_id="pv-1", artifacts=(), created_at="t0", scanner_executions=[],
    )

    with pytest.raises(AnalysisNotCompleteError):
        generate_report(analysis, "devsecops", generated_at="t1")
