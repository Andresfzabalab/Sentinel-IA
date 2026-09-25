"""Proves the Report Generation Service (moved here in Phase 9 from
core/application/ -- Module_Boundaries.md assigns "Reporting (full report)"
to the AI & Agent Module): redaction for the developer audience, the
409-mapped "not complete yet" error, and the AI Enrichment join that makes
`aiSection.status` reflect the real Agent Execution state.
"""

from __future__ import annotations

import pytest

from sentinel.ai_agent.application.report_generation_service import (
    AnalysisNotCompleteError,
    ReportGenerationService,
)
from sentinel.ai_agent.domain.entities import AgentExecution, ExecutionLimits
from sentinel.ai_agent.domain.value_objects import AIEnrichment
from sentinel.ai_agent.ports.security_result_query_port import FindingView, SecurityResultView


class FakeSecurityResultQueryPort:
    def __init__(self) -> None:
        self._results: dict[str, SecurityResultView] = {}

    def put(self, view: SecurityResultView) -> None:
        self._results[view.analysis_id] = view

    def get(self, analysis_id: str) -> SecurityResultView | None:
        return self._results.get(analysis_id)


class FakeAgentExecutionStore:
    def __init__(self) -> None:
        self._enrichments: dict[str, list[AIEnrichment]] = {}
        self._executions: dict[str, AgentExecution] = {}

    def start(self, execution: AgentExecution) -> None:
        self._executions[execution.subject_analysis_id] = execution

    def complete(self, execution: AgentExecution) -> None:
        self._executions[execution.subject_analysis_id] = execution

    def add_enrichment(self, enrichment: AIEnrichment) -> None:
        self._enrichments.setdefault(enrichment.subject_id, []).append(enrichment)

    def get_enrichments_for_subject(self, subject_id: str) -> tuple[AIEnrichment, ...]:
        return tuple(self._enrichments.get(subject_id, ()))

    def get_latest_execution(self, subject_analysis_id: str) -> AgentExecution | None:
        return self._executions.get(subject_analysis_id)


def _security_result_with_a_secret_finding(analysis_id: str = "an-1") -> SecurityResultView:
    secret_finding = FindingView(
        finding_id="f-1", scanner_id="gitleaks", category="secret", artifact_path="config.py",
        rule_or_check_id="aws-key", severity_level="critical", risk_level="critical",
        secret_value_redaction_flag=True,
    )
    ordinary_finding = FindingView(
        finding_id="f-2", scanner_id="semgrep", category="sast", artifact_path="app.py",
        rule_or_check_id="r1", severity_level="high", risk_level="high",
        secret_value_redaction_flag=False,
    )
    return SecurityResultView(
        analysis_id=analysis_id, correlation_id="corr-1", findings=(secret_finding, ordinary_finding),
        security_score=40.0, policy_version_id="pv-1", verdict="BLOCK", triggered_rules=("r1",),
        completed_at="t2", degradation_any_scanner_failed=False, degradation_ai_available_at_completion=False,
    )


def _service() -> tuple[ReportGenerationService, FakeSecurityResultQueryPort, FakeAgentExecutionStore]:
    query_port = FakeSecurityResultQueryPort()
    execution_store = FakeAgentExecutionStore()
    return ReportGenerationService(query_port, execution_store), query_port, execution_store


def test_devsecops_report_includes_every_finding() -> None:
    service, query_port, _ = _service()
    query_port.put(_security_result_with_a_secret_finding())

    report = service.generate("an-1", "devsecops", generated_at="t3")

    assert len(report.content["findings"]) == 2
    assert report.content["verdict"] == "BLOCK"
    assert report.content["triggeredRules"] == ["r1"]


def test_developer_report_excludes_secret_flagged_findings() -> None:
    service, query_port, _ = _service()
    query_port.put(_security_result_with_a_secret_finding())

    report = service.generate("an-1", "developer", generated_at="t3")

    assert len(report.content["findings"]) == 1
    assert report.content["findings"][0]["ruleOrCheckId"] == "r1"
    assert report.content["triggeredRules"] == []  # rule detail withheld from developer view


def test_ai_section_is_pending_with_no_agent_execution() -> None:
    service, query_port, _ = _service()
    query_port.put(_security_result_with_a_secret_finding())

    report = service.generate("an-1", "devsecops", generated_at="t3")

    assert report.ai_section == {"status": "pending", "contentRef": None}


def test_ai_section_is_complete_once_an_agent_execution_finished_and_enrichments_are_joined() -> None:
    service, query_port, execution_store = _service()
    query_port.put(_security_result_with_a_secret_finding())

    execution = AgentExecution(
        id="ae-1", subject_analysis_id="an-1", correlation_id="corr-1", agent_type="security-investigation",
        execution_limits=ExecutionLimits(max_duration_seconds=30, max_tool_calls=10, max_output_size=1000),
        started_at="t1",
    )
    execution.complete("t2")
    execution_store.complete(execution)
    execution_store.add_enrichment(
        AIEnrichment(
            id="enr-1", scope="finding", subject_id="f-2", explanation="This SAST finding means...",
            remediation_status="provided", source_agent_execution_id="ae-1", created_at="t2",
            remediation_suggestion="Use parameterized queries.",
        )
    )

    report = service.generate("an-1", "devsecops", generated_at="t3")

    assert report.ai_section == {"status": "complete", "contentRef": "ae-1"}
    ordinary = next(f for f in report.content["findings"] if f["findingId"] == "f-2")
    assert ordinary["aiExplanation"] == "This SAST finding means..."
    assert ordinary["aiRemediationSuggestion"] == "Use parameterized queries."
    secret = next(f for f in report.content["findings"] if f["findingId"] == "f-1")
    assert secret["aiExplanation"] is None


def test_requesting_a_report_for_an_analysis_with_no_security_result_raises() -> None:
    service, _, _ = _service()

    with pytest.raises(AnalysisNotCompleteError):
        service.generate("an-missing", "devsecops", generated_at="t1")
