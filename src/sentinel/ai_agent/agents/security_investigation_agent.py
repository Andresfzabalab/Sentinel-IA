"""Security Investigation Agent -- the first agent registered in the
Agent Execution Framework (AI_Agent_Architecture.md §4). Its role is to
investigate and explain an already-completed Security Result -- not to
test, scan, or decide anything. It never orchestrates or re-runs scanners,
never modifies any Finding/Risk/Score/Policy outcome, and every tool it
reads from is read-only by construction.
"""

from __future__ import annotations

from dataclasses import dataclass

from sentinel.ai_agent.agents.framework import AgentExecutionContext
from sentinel.ai_agent.agents.tools import (
    READ_FINDINGS_TOOL,
    READ_KNOWLEDGE_BASE_TOOL,
    READ_RISK_BREAKDOWN_TOOL,
    READ_SECURITY_SCORE_TOOL,
    KnowledgeBaseTool,
    read_findings,
    read_risk_breakdown,
    read_security_score,
)
from sentinel.ai_agent.domain.value_objects import AIEnrichment
from sentinel.ai_agent.ports.ai_provider_port import AdvisoryRequest, AIProviderPort, AIProviderUnavailable
from sentinel.ai_agent.ports.security_result_query_port import SecurityResultView

AGENT_TYPE = "security-investigation"


@dataclass(frozen=True)
class InvestigationResult:
    enrichments: tuple[AIEnrichment, ...]
    knowledge_base_entries_used: tuple[tuple[str, int], ...]


class SecurityInvestigationAgent:
    def __init__(self, ai_provider: AIProviderPort, knowledge_base_tool: KnowledgeBaseTool) -> None:
        self._ai_provider = ai_provider
        self._knowledge_base_tool = knowledge_base_tool

    def investigate(
        self,
        context: AgentExecutionContext,
        security_result: SecurityResultView,
        *,
        enrichment_id_factory,
        agent_execution_id: str,
        created_at: str,
    ) -> InvestigationResult:
        """Raises AIProviderUnavailable if the provider cannot be reached --
        the caller (Agent Execution Runner) is responsible for turning that
        into `pending_unavailable`, never a partial/half-written result.
        """
        findings = context.call_tool(READ_FINDINGS_TOOL, read_findings, security_result)
        risk_breakdown = dict(context.call_tool(READ_RISK_BREAKDOWN_TOOL, read_risk_breakdown, security_result))
        context.call_tool(READ_SECURITY_SCORE_TOOL, read_security_score, security_result)

        enrichments: list[AIEnrichment] = []
        kb_entries_used: list[tuple[str, int]] = []

        for finding in findings:
            if finding.secret_value_redaction_flag:
                # A raw secret value must never reach an LLM prompt --
                # advisory text for a secret finding stays generic, no
                # tool call needed to justify it.
                continue

            kb_entry = context.call_tool(READ_KNOWLEDGE_BASE_TOOL, self._knowledge_base_tool, finding.category)

            request = AdvisoryRequest(
                finding_category=finding.category,
                finding_rule_or_check_id=finding.rule_or_check_id,
                finding_severity_level=finding.severity_level,
                finding_risk_level=risk_breakdown.get(finding.finding_id),
                artifact_path=finding.artifact_path,
                knowledge_base_content=kb_entry.content if kb_entry else None,
            )
            advisory = self._ai_provider.generate_advisory(request)  # may raise AIProviderUnavailable

            if kb_entry is not None:
                kb_entries_used.append((kb_entry.topic, kb_entry.version))

            enrichments.append(
                AIEnrichment(
                    id=enrichment_id_factory(),
                    scope="finding",
                    subject_id=finding.finding_id,
                    explanation=advisory.explanation,
                    consequence_framing=advisory.consequence_framing,
                    prioritization_hint=advisory.prioritization_hint,
                    remediation_suggestion=advisory.remediation_suggestion if kb_entry is not None else None,
                    remediation_status="provided" if kb_entry is not None else "insufficient_knowledge",
                    knowledge_base_entries_cited=((kb_entry.topic, kb_entry.version),) if kb_entry else (),
                    source_agent_execution_id=agent_execution_id,
                    created_at=created_at,
                )
            )

        return InvestigationResult(enrichments=tuple(enrichments), knowledge_base_entries_used=tuple(kb_entries_used))
