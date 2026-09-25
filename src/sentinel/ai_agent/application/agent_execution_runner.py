"""Agent Execution Runner -- UC-7. Drives one Security Investigation Agent
run end to end: pulls the Security Result via SecurityResultQueryPort,
enforces execution limits via the Agent Execution Framework, logs tool
calls, and hands the result to persistence. Application/Orchestration
Service (Domain_Services.md): it orchestrates, the actual advisory content
comes from the AI Enrichment via the Security Investigation Agent, not from
this runner.

Triggered by `AnalysisCompleted`, arriving through the AnalysisCompletedRelay
(Domain_Events.md) -- by the time this runs, the Security Result is already
final and frozen; nothing here can alter it (P-02).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sentinel.ai_agent.agents.framework import AgentDefinition, AgentExecutionContext, AgentRegistry
from sentinel.ai_agent.agents.security_investigation_agent import SecurityInvestigationAgent
from sentinel.ai_agent.domain.entities import AgentExecution
from sentinel.ai_agent.ports.ai_provider_port import AIProviderUnavailable
from sentinel.ai_agent.ports.security_result_query_port import SecurityResultQueryPort
from sentinel.ai_agent.ports.store_ports import AgentExecutionStore, AuditRecorderPort
from sentinel.core.domain.audit.entities import AuditRecord
from sentinel.shared.logging import get_logger

_logger = get_logger("ai_agent", "AgentExecutionRunner")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentExecutionRunner:
    def __init__(
        self,
        agent_registry: AgentRegistry,
        security_investigation_agent: SecurityInvestigationAgent,
        security_result_query_port: SecurityResultQueryPort,
        agent_execution_store: AgentExecutionStore,
        audit_recorder_port: AuditRecorderPort,
        *,
        agent_type: str,
        id_factory: "callable[[], str]" = lambda: str(uuid.uuid4()),
        clock: "callable[[], str]" = _utc_now_iso,
    ) -> None:
        self._agent_registry = agent_registry
        self._agent = security_investigation_agent
        self._security_result_query_port = security_result_query_port
        self._agent_execution_store = agent_execution_store
        self._audit_recorder_port = audit_recorder_port
        self._agent_type = agent_type
        self._id_factory = id_factory
        self._clock = clock

    def run(self, analysis_id: str, correlation_id: str) -> None:
        """Never raises -- every failure mode (missing Security Result,
        provider unavailable, execution-limit exceeded) resolves to a
        recorded, terminal AgentExecution state. Called from the
        AnalysisCompletedRelay handler, which must never let an agent
        failure propagate back toward the Orchestrator (Module_Boundaries.md's
        one-way dependency direction: nothing here can call back upstream).
        """
        security_result = self._security_result_query_port.get(analysis_id)
        if security_result is None:
            return  # nothing to investigate -- e.g. a 'failed' Analysis with no Security Result at all

        definition = self._agent_registry.get(self._agent_type)
        execution = AgentExecution(
            id=self._id_factory(),
            subject_analysis_id=analysis_id,
            correlation_id=correlation_id,
            agent_type=self._agent_type,
            execution_limits=definition.execution_limits,
            started_at=self._clock(),
        )
        self._agent_execution_store.start(execution)
        self._record_audit(execution, "AgentExecutionStarted", {})
        _logger.info(
            "agent_execution_started", f"Agent execution {execution.id} started for analysis {analysis_id}",
            correlation_id=correlation_id, analysis_id=analysis_id, agent_execution_id=execution.id,
        )

        context = AgentExecutionContext(definition=definition, clock=self._clock)

        try:
            result = self._agent.investigate(
                context, security_result,
                enrichment_id_factory=self._id_factory, agent_execution_id=execution.id, created_at=self._clock(),
            )
        except AIProviderUnavailable as exc:
            execution.tool_calls_log = list(context.tool_calls)
            execution.mark_pending_unavailable()
            self._agent_execution_store.complete(execution)
            self._record_audit(execution, "AgentExecutionPending", {"reason": "ai_provider_unavailable"})
            _logger.warning(
                "agent_execution_pending_unavailable", f"AI provider unavailable: {exc}",
                correlation_id=correlation_id, analysis_id=analysis_id, agent_execution_id=execution.id,
            )
            return
        except Exception as exc:  # noqa: BLE001 -- a framework/agent bug must never propagate upstream (see docstring)
            execution.tool_calls_log = list(context.tool_calls)
            execution.mark_pending_unavailable()
            self._agent_execution_store.complete(execution)
            self._record_audit(execution, "AgentExecutionPending", {"reason": f"unexpected_error: {exc}"})
            _logger.error(
                "agent_execution_unexpected_error", f"Agent execution {execution.id} failed unexpectedly: {exc}",
                correlation_id=correlation_id, analysis_id=analysis_id, agent_execution_id=execution.id,
            )
            return

        for enrichment in result.enrichments:
            self._agent_execution_store.add_enrichment(enrichment)

        execution.tool_calls_log = list(context.tool_calls)
        execution.knowledge_base_entries_used = list(result.knowledge_base_entries_used)
        execution.complete(self._clock())
        self._agent_execution_store.complete(execution)
        self._record_audit(
            execution, "AgentExecutionCompleted",
            {"enrichmentCount": len(result.enrichments), "knowledgeBaseEntriesUsed": list(result.knowledge_base_entries_used)},
        )
        _logger.info(
            "agent_execution_completed", f"Agent execution {execution.id} completed with {len(result.enrichments)} enrichment(s)",
            correlation_id=correlation_id, analysis_id=analysis_id, agent_execution_id=execution.id,
        )

    def _record_audit(self, execution: AgentExecution, event_type: str, extra_payload: dict) -> None:
        self._audit_recorder_port.append(
            AuditRecord(
                id=f"{execution.id}-{event_type}",
                actor="system",
                event_type=event_type,
                origin="llm-agent",
                payload={
                    "agentExecutionId": execution.id,
                    "agentType": execution.agent_type,
                    "toolCalls": [c.tool_name for c in execution.tool_calls_log],
                    **extra_payload,
                },
                created_at=self._clock(),
                subject_analysis_id=execution.subject_analysis_id,
                correlation_id=execution.correlation_id,
            )
        )
