"""Report Generation -- UC-5. Module_Boundaries.md's Bounded Context ->
Module mapping assigns "Reporting (full report)" to the AI & Agent Module,
since a Report must join the Security Result with the Security
Investigation Agent's contribution. Moved here from
core/application/report_generation_service.py (Phase 8) precisely because
that placement made Sentinel Core the module joining AI Enrichment data --
the opposite of Module_Boundaries.md's fixed one-way dependency direction
("Sentinel Core depends on nothing else in this diagram"). This version
depends only on ai_agent/ports/ (SecurityResultQueryPort, cross-module
read-only) plus this module's own AgentExecutionStore -- never on
core/domain/ or core/application/ directly.

A Report is always regenerable and disposable (Ubiquitous_Language.md) --
this service never persists anything, it only projects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sentinel.ai_agent.ports.security_result_query_port import SecurityResultQueryPort
from sentinel.ai_agent.ports.store_ports import AgentExecutionStore

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


class ReportGenerationService:
    def __init__(
        self,
        security_result_query_port: SecurityResultQueryPort,
        agent_execution_store: AgentExecutionStore,
    ) -> None:
        self._security_result_query_port = security_result_query_port
        self._agent_execution_store = agent_execution_store

    def generate(self, analysis_id: str, audience: Audience, *, generated_at: str) -> Report:
        security_result = self._security_result_query_port.get(analysis_id)
        if security_result is None:
            raise AnalysisNotCompleteError(f"analysis {analysis_id!r} has no Security Result yet")

        findings_view = []
        for f in security_result.findings:
            # A raw secret value is never captured anywhere upstream (Gitleaks'
            # adapter, Phase 5) -- this filter is a second, structural guard
            # that no secret-flagged finding's location/content leaks to the
            # Developer audience beyond what Input_Output_Model.md allows.
            if audience != "devsecops" and f.secret_value_redaction_flag:
                continue

            enrichments = self._agent_execution_store.get_enrichments_for_subject(f.finding_id)
            enrichment = enrichments[-1] if enrichments else None

            findings_view.append(
                {
                    "findingId": f.finding_id,
                    "scannerId": f.scanner_id,
                    "category": f.category,
                    "artifactPath": f.artifact_path,
                    "ruleOrCheckId": f.rule_or_check_id,
                    "severityLevel": f.severity_level,
                    "riskLevel": f.risk_level,
                    "correlationGroupId": f.correlation_group_id,
                    "location": (
                        {"file": f.location_file, "lineStart": f.location_line_start, "lineEnd": f.location_line_end}
                        if f.location_file
                        else None
                    ),
                    "aiExplanation": enrichment.explanation if enrichment else None,
                    "aiConsequenceFraming": enrichment.consequence_framing if enrichment else None,
                    "aiPrioritizationHint": enrichment.prioritization_hint if enrichment else None,
                    "aiRemediationSuggestion": enrichment.remediation_suggestion if enrichment else None,
                    "aiRemediationStatus": enrichment.remediation_status if enrichment else None,
                }
            )

        content: dict[str, Any] = {
            "verdict": security_result.verdict,
            "securityScore": security_result.security_score,
            "policyVersionId": security_result.policy_version_id,
            "triggeredRules": list(security_result.triggered_rules) if audience == "devsecops" else [],
            "degradation": {
                "anyScannerFailed": security_result.degradation_any_scanner_failed,
                "aiAvailableAtCompletion": security_result.degradation_ai_available_at_completion,
            },
            "findings": findings_view,
        }

        agent_execution = self._agent_execution_store.get_latest_execution(analysis_id)
        if agent_execution is not None and agent_execution.status == "completed":
            ai_section = {"status": "complete", "contentRef": agent_execution.id}
        else:
            ai_section = {"status": "pending", "contentRef": None}

        return Report(
            report_id=f"{analysis_id}-report-{audience}",
            analysis_id=analysis_id,
            audience=audience,
            content=content,
            ai_section=ai_section,
            format="json",
            generated_at=generated_at,
        )
