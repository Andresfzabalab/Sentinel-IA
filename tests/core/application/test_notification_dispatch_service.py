"""Proves the Notification Dispatch Service (Phase 10, extracted from the
Orchestrator per Domain_Services.md): the mandatory GitHub status check and
the redacted summary comment are both delivered for a completed, PR-linked
Analysis; neither is delivered for a Mode B trigger (no PR); a delivery
failure is recorded as `failed`, never raised; and the comment body never
contains raw secret values or per-finding location detail.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from sentinel.core.application.notification_dispatch_service import (
    NotificationDispatchService,
    build_summary_comment_markdown,
)
from sentinel.core.domain.analysis.entities import Analysis, Finding, ScannerExecution
from sentinel.core.domain.analysis.value_objects import PullRequestSnapshot, Risk, SecurityScore, Severity, Verdict
from sentinel.core.domain.notification.entities import Notification
from sentinel.core.ports.repository_port import AnalysisResultSummary


@dataclass
class _Repository:
    external_identifier: str = "acme/widgets"


class FakeRepositoryPort:
    def __init__(self) -> None:
        self.published_results: list[tuple] = []
        self.published_comments: list[tuple] = []
        self.status_should_fail = False
        self.comment_should_fail = False

    def publish_result(self, repository_external_id: str, head_commit_sha: str, result: AnalysisResultSummary) -> bool:
        self.published_results.append((repository_external_id, head_commit_sha, result))
        return not self.status_should_fail

    def publish_summary_comment(self, repository_external_id: str, pr_number: int, body: str) -> bool:
        self.published_comments.append((repository_external_id, pr_number, body))
        return not self.comment_should_fail


class FakeNotificationStore:
    def __init__(self) -> None:
        self.attempts: list[Notification] = []

    def record_attempt(self, notification: Notification) -> None:
        self.attempts.append(notification)


def _pr_snapshot(pr_number: int = 42) -> PullRequestSnapshot:
    return PullRequestSnapshot(
        provider="github", pr_number=pr_number, base_branch="main", head_branch="feature",
        author="dana", head_commit_sha="sha-1", changed_file_paths=("app.py",),
    )


def _completed_analysis_with_findings(pr_snapshot: PullRequestSnapshot | None) -> Analysis:
    analysis = Analysis.start(
        id="an-1", correlation_id="corr-1", trigger_mode="mode_a" if pr_snapshot else "mode_b",
        repository_id="repo-1", policy_version_id="pv-1", artifacts=(), created_at="t0",
        pr_snapshot=pr_snapshot,
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


def _service(repository_port=None, notification_store=None):
    repository_port = repository_port or FakeRepositoryPort()
    notification_store = notification_store or FakeNotificationStore()
    service = NotificationDispatchService(repository_port, notification_store, clock=lambda: "t3")
    return service, repository_port, notification_store


def test_dispatch_for_a_mode_a_analysis_delivers_both_status_and_comment() -> None:
    service, repository_port, notification_store = _service()
    analysis = _completed_analysis_with_findings(_pr_snapshot())

    service.dispatch_for_completed_analysis(_Repository(), analysis)

    assert len(repository_port.published_results) == 1
    assert len(repository_port.published_comments) == 1
    assert repository_port.published_comments[0][1] == 42  # pr_number
    channels = {n.channel: n.status for n in notification_store.attempts}
    assert channels == {"github-status": "delivered", "github-comment": "delivered"}


def test_dispatch_for_a_mode_b_analysis_delivers_nothing() -> None:
    service, repository_port, notification_store = _service()
    analysis = _completed_analysis_with_findings(pr_snapshot=None)

    service.dispatch_for_completed_analysis(_Repository(), analysis)

    assert repository_port.published_results == []
    assert repository_port.published_comments == []
    assert notification_store.attempts == []


def test_a_comment_delivery_failure_is_recorded_as_failed_never_raised() -> None:
    repository_port = FakeRepositoryPort()
    repository_port.comment_should_fail = True
    service, _, notification_store = _service(repository_port=repository_port)
    analysis = _completed_analysis_with_findings(_pr_snapshot())

    service.dispatch_for_completed_analysis(_Repository(), analysis)  # must not raise

    channels = {n.channel: n.status for n in notification_store.attempts}
    assert channels["github-comment"] == "failed"
    assert channels["github-status"] == "delivered"


def test_summary_comment_never_contains_the_raw_secret_or_finding_locations() -> None:
    analysis = _completed_analysis_with_findings(_pr_snapshot())

    body = build_summary_comment_markdown(analysis)

    assert "config.py" not in body  # the secret-flagged finding's artifact path never appears
    assert "app.py" not in body  # nor the ordinary finding's -- this is an aggregate view only
    assert "BLOCK" in body
    assert "Critical: 1" in body
    assert "High: 1" in body


def test_summary_comment_reports_no_findings_cleanly() -> None:
    analysis = Analysis.start(
        id="an-2", correlation_id="corr-2", trigger_mode="mode_a", repository_id="repo-1",
        policy_version_id="pv-1", artifacts=(), created_at="t0", pr_snapshot=_pr_snapshot(),
        scanner_executions=[],
    )
    analysis.record_verdict(
        Verdict(value="PASS", policy_version_id="pv-1", triggered_rules=()),
        SecurityScore(value=100.0),
        degradation_any_scanner_failed=False, degradation_ai_available_at_completion=False,
        completed_at="t1",
    )

    body = build_summary_comment_markdown(analysis)

    assert "PASS" in body
    assert "No findings." in body


def test_deliver_status_isolates_a_repository_port_exception_as_a_failed_notification() -> None:
    class RaisingRepositoryPort:
        def publish_result(self, *args, **kwargs):
            raise RuntimeError("network exploded")

        def publish_summary_comment(self, *args, **kwargs):
            raise RuntimeError("network exploded")

    service, _, notification_store = _service(repository_port=RaisingRepositoryPort())

    service.deliver_status("acme/widgets", "sha-1", "an-3", AnalysisResultSummary(verdict="ERROR", description="x"))

    assert notification_store.attempts[0].status == "failed"
