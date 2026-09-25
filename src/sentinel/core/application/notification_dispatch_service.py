"""Notification Dispatch Service (Domain_Services.md) -- delivers the
mandatory, Sentinel-Core-owned Developer-facing channel: the GitHub status
check and the redacted summary PR comment (Module_Boundaries.md: "the
mandatory Developer-facing GitHub status check and summary comment are
minimal, deterministic, and emitted by Sentinel Core immediately upon a
PASS/BLOCK verdict -- they never wait on AI"). Pure I/O coordination: it
applies no business rule, only formatting/redaction and delivery-outcome
recording (`Domain_Services.md`'s Application/Orchestration Service
classification).

Extracted out of the Analysis Orchestrator so the Orchestrator stays a thin
coordinator (P-01) and this concern is independently testable/addressable,
per `Domain_Services.md`'s own explicit listing of "Notification Dispatch
Service" as a distinct Application Service.
"""

from __future__ import annotations

from collections import Counter

from sentinel.core.domain.analysis.entities import Analysis
from sentinel.core.domain.notification.entities import Notification
from sentinel.core.ports.repository_port import AnalysisResultSummary, RepositoryPort
from sentinel.core.ports.store_ports import NotificationStore


class NotificationDispatchService:
    def __init__(self, repository_port: RepositoryPort, notification_store: NotificationStore, *, clock) -> None:
        self._repository_port = repository_port
        self._notification_store = notification_store
        self._clock = clock

    def dispatch_for_completed_analysis(self, repository, analysis: Analysis) -> None:
        """The mandatory channel for a normally-completed Analysis: status
        check always, summary comment only when there is a PR to comment on
        (Mode A) -- Mode B has no PR (GitHub_Integration.md's "Comments").
        """
        if analysis.pr_snapshot is None:
            return  # Mode B has no PR / commit to post a status or comment against

        description = (
            "No blocking findings" if analysis.verdict.value == "PASS"
            else f"Blocked: {len(analysis.verdict.triggered_rules)} triggered rule(s)"
        )
        self.deliver_status(
            repository.external_identifier,
            analysis.pr_snapshot.head_commit_sha,
            analysis.id,
            AnalysisResultSummary(verdict=analysis.verdict.value, description=description),
        )
        self._deliver_summary_comment(repository.external_identifier, analysis)

    def deliver_status(
        self, external_identifier: str, head_commit_sha: str, analysis_id: str, result: AnalysisResultSummary
    ) -> None:
        try:
            delivered = self._repository_port.publish_result(external_identifier, head_commit_sha, result)
        except Exception:  # noqa: BLE001 -- a Notification failure must never affect the verdict already decided
            delivered = False

        self._record_attempt(analysis_id, "github-status", delivered, f'{{"verdict": "{result.verdict}", "description": "{result.description}"}}')

    def _deliver_summary_comment(self, external_identifier: str, analysis: Analysis) -> None:
        body = build_summary_comment_markdown(analysis)
        try:
            delivered = self._repository_port.publish_summary_comment(
                external_identifier, analysis.pr_snapshot.pr_number, body
            )
        except Exception:  # noqa: BLE001 -- same Notification-not-verdict isolation as the status channel
            delivered = False

        self._record_attempt(analysis.id, "github-comment", delivered, body)

    def _record_attempt(self, analysis_id: str, channel: str, delivered: bool, content_snapshot: str) -> None:
        self._notification_store.record_attempt(
            Notification(
                id=f"{analysis_id}-notif-{channel}-{self._clock()}",
                analysis_id=analysis_id,
                channel=channel,
                status="delivered" if delivered else "failed",
                attempted_at=self._clock(),
                content_snapshot=content_snapshot,
            )
        )


def build_summary_comment_markdown(analysis: Analysis) -> str:
    """The redacted, aggregated overview (Input_Output_Model.md: "Aggregated,
    non-sensitive overview") -- counts only, never a raw secret value, a
    file path, or a line number. Full per-finding detail is DevSecOps-only,
    behind the Reporting/Audit access boundary (Input_Output_Model.md's
    redaction rule).
    """
    verdict = analysis.verdict.value
    icon = "✅" if verdict == "PASS" else "🚫"
    lines = [f"## {icon} SentinelAI Security Analysis: {verdict}", "", f"**Security Score**: {analysis.security_score.value}"]

    if not analysis.findings:
        lines.append("")
        lines.append("No findings.")
        return "\n".join(lines)

    by_severity = Counter(f.severity.level for f in analysis.findings)
    lines.append("")
    lines.append("**Findings by severity**:")
    for level in ("critical", "high", "medium", "low"):
        if by_severity.get(level):
            lines.append(f"- {level.capitalize()}: {by_severity[level]}")

    if verdict == "BLOCK":
        lines.append("")
        lines.append(f"**Triggered policy rules**: {len(analysis.verdict.triggered_rules)}")

    lines.append("")
    lines.append("_Full finding detail is available to DevSecOps via the report endpoint._")
    return "\n".join(lines)
