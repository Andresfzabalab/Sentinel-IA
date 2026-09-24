"""Report Generation -- UC-5's callable operation. Phase 8 scope only: a
Report projection built purely from the frozen Security Result (the
Analysis Aggregate once `status = completed`), since AI Enrichment doesn't
exist until Phase 9 -- `aiSection.status` is therefore always "pending"
here. Phase 10 extends this to actually join Agent Execution output
(Data_Contracts.md's Report contract, Cross-Contract Consistency Rule 2).

A Report is always regenerable and disposable (Ubiquitous_Language.md) --
this service never persists anything, it only projects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sentinel.core.domain.analysis.entities import Analysis

Audience = Literal["developer", "devsecops"]


@dataclass(frozen=True)
class Report:
    report_id: str
    analysis_id: str
    audience: Audience
    content: dict[str, Any]
    ai_section: dict[str, Any]
    format: str
    generated_at: str


class AnalysisNotCompleteError(RuntimeError):
    """Raised when a Report is requested for an Analysis with no Security
    Result yet -- API_Contract.md's `GET /analyses/{id}/report` maps this
    to 409, "not ready yet", never "the Analysis failed".
    """


def generate_report(analysis: Analysis, audience: Audience, *, generated_at: str) -> Report:
    if analysis.status != "completed":
        raise AnalysisNotCompleteError(f"analysis {analysis.id!r} has no Security Result yet (status={analysis.status!r})")

    findings_view = [
        {
            "findingId": f.id,
            "scannerId": f.scanner_id,
            "category": f.category,
            "artifactPath": f.artifact_path,
            "ruleOrCheckId": f.rule_or_check_id,
            "severityLevel": f.severity.level,
            "riskLevel": f.risk.adjusted_level if f.risk else None,
            "correlationGroupId": f.correlation_group_id,
            "location": (
                {"file": f.location_file, "lineStart": f.location_line_start, "lineEnd": f.location_line_end}
                if f.location_file
                else None
            ),
        }
        for f in analysis.findings
        # A raw secret value is never captured anywhere upstream (Gitleaks'
        # adapter, Phase 5) -- this filter is a second, structural guard
        # that no secret-flagged finding's location/content leaks to the
        # Developer audience beyond what Input_Output_Model.md allows.
        if audience == "devsecops" or not f.secret_value_redaction_flag
    ]

    content: dict[str, Any] = {
        "verdict": analysis.verdict.value,
        "securityScore": analysis.security_score.value,
        "policyVersionId": analysis.policy_version_id,
        "triggeredRules": list(analysis.verdict.triggered_rules) if audience == "devsecops" else [],
        "degradation": {
            "anyScannerFailed": analysis.degradation_any_scanner_failed,
            "aiAvailableAtCompletion": analysis.degradation_ai_available_at_completion,
        },
        "findings": findings_view,
    }

    return Report(
        report_id=f"{analysis.id}-report-{audience}",
        analysis_id=analysis.id,
        audience=audience,
        content=content,
        ai_section={"status": "pending", "contentRef": None},
        format="json",
        generated_at=generated_at,
    )
