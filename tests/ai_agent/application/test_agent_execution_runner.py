"""Proves the Agent Execution Runner (UC-7): never raises, records the
right terminal AgentExecution state (completed / pending_unavailable) for
every outcome, and -- the single most important test in Phase 9 -- that an
AI provider outage never touches the Security Result it references (P-02:
AI is advisory-only; QA-04: graceful degradation).
"""

from __future__ import annotations

from sentinel.ai_agent.agents.framework import AgentDefinition, AgentRegistry
from sentinel.ai_agent.agents.security_investigation_agent import AGENT_TYPE, SecurityInvestigationAgent
from sentinel.ai_agent.agents.tools import ALL_TOOL_NAMES, KnowledgeBaseTool
from sentinel.ai_agent.application.agent_execution_runner import AgentExecutionRunner
from sentinel.ai_agent.domain.entities import AgentExecution, ExecutionLimits
from sentinel.ai_agent.domain.value_objects import AIEnrichment
from sentinel.ai_agent.ports.ai_provider_port import AdvisoryResponse, AIProviderUnavailable
from sentinel.ai_agent.ports.security_result_query_port import FindingView, SecurityResultView
from sentinel.core.domain.audit.entities import AuditRecord


class FakeSecurityResultQueryPort:
    def __init__(self, view: SecurityResultView | None) -> None:
        self._view = view

    def get(self, analysis_id: str) -> SecurityResultView | None:
        return self._view


class FakeAgentExecutionStore:
    def __init__(self) -> None:
        self.started: list[AgentExecution] = []
        self.completed: list[AgentExecution] = []
        self.enrichments: list[AIEnrichment] = []

    def start(self, execution: AgentExecution) -> None:
        self.started.append(execution)

    def complete(self, execution: AgentExecution) -> None:
        self.completed.append(execution)

    def add_enrichment(self, enrichment: AIEnrichment) -> None:
        self.enrichments.append(enrichment)

    def get_enrichments_for_subject(self, subject_id: str) -> tuple[AIEnrichment, ...]:
        return tuple(e for e in self.enrichments if e.subject_id == subject_id)

    def get_latest_execution(self, subject_analysis_id: str) -> AgentExecution | None:
        return self.completed[-1] if self.completed else None


class FakeAuditRecorderPort:
    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    def append(self, record: AuditRecord) -> None:
        self.records.append(record)


class FakeKnowledgeBasePort:
    def find_relevant(self, topic: str):
        return None


class AlwaysUnavailableAIProvider:
    def generate_advisory(self, request):
        raise AIProviderUnavailable("simulated outage")


class AlwaysSucceedsAIProvider:
    def generate_advisory(self, request):
        return AdvisoryResponse(explanation="explanation text")


def _security_result_with_one_ordinary_finding(analysis_id: str = "an-1") -> SecurityResultView:
    finding = FindingView(
        finding_id="f-1", scanner_id="semgrep", category="sast", artifact_path="app.py",
        rule_or_check_id="r1", severity_level="high", risk_level="high",
        secret_value_redaction_flag=False,
    )
    return SecurityResultView(
        analysis_id=analysis_id, correlation_id="corr-1", findings=(finding,), security_score=60.0,
        policy_version_id="pv-1", verdict="BLOCK", triggered_rules=("r1",), completed_at="t2",
        degradation_any_scanner_failed=False, degradation_ai_available_at_completion=True,
    )


def _runner(ai_provider, security_result_view, execution_store=None, audit_recorder=None):
    registry = AgentRegistry()
    registry.register(
        AgentDefinition(
            agent_type=AGENT_TYPE, allowed_tools=ALL_TOOL_NAMES,
            execution_limits=ExecutionLimits(max_duration_seconds=30, max_tool_calls=50, max_output_size=4000),
        )
    )
    agent = SecurityInvestigationAgent(ai_provider, KnowledgeBaseTool(FakeKnowledgeBasePort()))
    execution_store = execution_store or FakeAgentExecutionStore()
    audit_recorder = audit_recorder or FakeAuditRecorderPort()
    runner = AgentExecutionRunner(
        registry, agent, FakeSecurityResultQueryPort(security_result_view), execution_store, audit_recorder,
        agent_type=AGENT_TYPE, id_factory=lambda: "ae-1", clock=lambda: "t3",
    )
    return runner, execution_store, audit_recorder


def test_run_with_no_security_result_does_nothing() -> None:
    runner, execution_store, audit_recorder = _runner(AlwaysSucceedsAIProvider(), None)

    runner.run("an-missing", "corr-1")

    assert execution_store.started == []
    assert audit_recorder.records == []


def test_run_with_a_working_provider_completes_with_enrichments() -> None:
    runner, execution_store, audit_recorder = _runner(
        AlwaysSucceedsAIProvider(), _security_result_with_one_ordinary_finding()
    )

    runner.run("an-1", "corr-1")

    assert execution_store.completed[-1].status == "completed"
    assert len(execution_store.enrichments) == 1
    event_types = [r.event_type for r in audit_recorder.records]
    assert event_types == ["AgentExecutionStarted", "AgentExecutionCompleted"]


def test_run_with_an_unavailable_provider_ends_pending_unavailable_never_raises() -> None:
    runner, execution_store, audit_recorder = _runner(
        AlwaysUnavailableAIProvider(), _security_result_with_one_ordinary_finding()
    )

    runner.run("an-1", "corr-1")  # must not raise

    assert execution_store.completed[-1].status == "pending_unavailable"
    assert execution_store.enrichments == []
    event_types = [r.event_type for r in audit_recorder.records]
    assert event_types == ["AgentExecutionStarted", "AgentExecutionPending"]


def test_an_ai_provider_outage_never_alters_the_already_frozen_security_result() -> None:
    """The critical QA-04/P-02 proof: the exact same SecurityResultView is
    handed to two runs, one with a working provider and one with a
    simulated outage. Whatever the AgentExecutionRunner does, it operates
    on a read-only view it never mutates and cannot write back to Sentinel
    Core -- so the verdict/security_score the caller already computed is
    identical in both cases, byte for byte.
    """
    security_result = _security_result_with_one_ordinary_finding()

    available_runner, _, _ = _runner(AlwaysSucceedsAIProvider(), security_result)
    available_runner.run("an-1", "corr-1")

    unavailable_runner, unavailable_store, _ = _runner(AlwaysUnavailableAIProvider(), security_result)
    unavailable_runner.run("an-1", "corr-1")

    # The view itself was never mutated by either run.
    assert security_result.verdict == "BLOCK"
    assert security_result.security_score == 60.0
    assert security_result.findings[0].risk_level == "high"

    # The outage produced a distinct, terminal, never-blocking state --
    # not a modified Security Result, not a raised exception, not a retry
    # that could delay anything downstream.
    assert unavailable_store.completed[-1].status == "pending_unavailable"
