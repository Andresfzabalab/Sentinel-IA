"""Proves the Security Investigation Agent's two core rules
(AI_Agent_Architecture.md §6/§7): a secret-flagged finding is never sent to
an LLM, and "bounded honesty" -- when no Knowledge Base entry exists, the
LLM's remediation suggestion is discarded and `remediation_status` becomes
`insufficient_knowledge`, no matter what the (fake) LLM returned.
"""

from __future__ import annotations

from sentinel.ai_agent.agents.framework import AgentDefinition, AgentExecutionContext
from sentinel.ai_agent.agents.security_investigation_agent import SecurityInvestigationAgent
from sentinel.ai_agent.agents.tools import ALL_TOOL_NAMES, KnowledgeBaseTool
from sentinel.ai_agent.domain.entities import ExecutionLimits
from sentinel.ai_agent.ports.ai_provider_port import AdvisoryResponse
from sentinel.ai_agent.ports.security_knowledge_base_port import KnowledgeBaseEntryView
from sentinel.ai_agent.ports.security_result_query_port import FindingView, SecurityResultView


class FakeAIProvider:
    def __init__(self, response: AdvisoryResponse) -> None:
        self._response = response
        self.requests = []

    def generate_advisory(self, request):
        self.requests.append(request)
        return self._response


class FakeKnowledgeBasePort:
    def __init__(self, entries: dict[str, KnowledgeBaseEntryView]) -> None:
        self._entries = entries

    def find_relevant(self, topic: str):
        return self._entries.get(topic)


def _context() -> AgentExecutionContext:
    definition = AgentDefinition(
        agent_type="security-investigation", allowed_tools=ALL_TOOL_NAMES,
        execution_limits=ExecutionLimits(max_duration_seconds=30, max_tool_calls=50, max_output_size=4000),
    )
    return AgentExecutionContext(definition=definition, clock=lambda: "t")


def _security_result(findings: tuple[FindingView, ...]) -> SecurityResultView:
    return SecurityResultView(
        analysis_id="an-1", correlation_id="corr-1", findings=findings, security_score=40.0,
        policy_version_id="pv-1", verdict="BLOCK", triggered_rules=("r1",), completed_at="t2",
        degradation_any_scanner_failed=False, degradation_ai_available_at_completion=False,
    )


def test_secret_flagged_findings_are_never_sent_to_the_ai_provider() -> None:
    secret_finding = FindingView(
        finding_id="f-1", scanner_id="gitleaks", category="secret", artifact_path="config.py",
        rule_or_check_id="aws-key", severity_level="critical", risk_level="critical",
        secret_value_redaction_flag=True,
    )
    ai_provider = FakeAIProvider(AdvisoryResponse(explanation="should never be called"))
    agent = SecurityInvestigationAgent(ai_provider, KnowledgeBaseTool(FakeKnowledgeBasePort({})))

    result = agent.investigate(
        _context(), _security_result((secret_finding,)),
        enrichment_id_factory=lambda: "enr-1", agent_execution_id="ae-1", created_at="t2",
    )

    assert ai_provider.requests == []
    assert result.enrichments == ()


def test_a_finding_with_no_knowledge_base_entry_gets_insufficient_knowledge_status() -> None:
    finding = FindingView(
        finding_id="f-2", scanner_id="semgrep", category="sast", artifact_path="app.py",
        rule_or_check_id="r1", severity_level="high", risk_level="high",
        secret_value_redaction_flag=False,
    )
    # The (fake) LLM tries to suggest a remediation anyway -- bounded
    # honesty means this must be discarded, never surfaced.
    ai_provider = FakeAIProvider(AdvisoryResponse(explanation="explanation text", remediation_suggestion="do this fix"))
    agent = SecurityInvestigationAgent(ai_provider, KnowledgeBaseTool(FakeKnowledgeBasePort({})))

    result = agent.investigate(
        _context(), _security_result((finding,)),
        enrichment_id_factory=lambda: "enr-1", agent_execution_id="ae-1", created_at="t2",
    )

    assert len(result.enrichments) == 1
    enrichment = result.enrichments[0]
    assert enrichment.remediation_status == "insufficient_knowledge"
    assert enrichment.remediation_suggestion is None
    assert enrichment.explanation == "explanation text"


def test_a_finding_with_a_knowledge_base_entry_gets_a_provided_remediation_and_citation() -> None:
    finding = FindingView(
        finding_id="f-3", scanner_id="semgrep", category="sast", artifact_path="app.py",
        rule_or_check_id="r1", severity_level="high", risk_level="high",
        secret_value_redaction_flag=False,
    )
    kb_entry = KnowledgeBaseEntryView(topic="sast", version=2, content="Use parameterized queries.")
    ai_provider = FakeAIProvider(AdvisoryResponse(explanation="explanation text", remediation_suggestion="do this fix"))
    agent = SecurityInvestigationAgent(ai_provider, KnowledgeBaseTool(FakeKnowledgeBasePort({"sast": kb_entry})))

    result = agent.investigate(
        _context(), _security_result((finding,)),
        enrichment_id_factory=lambda: "enr-1", agent_execution_id="ae-1", created_at="t2",
    )

    enrichment = result.enrichments[0]
    assert enrichment.remediation_status == "provided"
    assert enrichment.remediation_suggestion == "do this fix"
    assert enrichment.knowledge_base_entries_cited == (("sast", 2),)
    assert result.knowledge_base_entries_used == (("sast", 2),)
    assert ai_provider.requests[0].knowledge_base_content == "Use parameterized queries."
