"""SqliteAgentExecutionStoreAdapter -- implements the domain-facing
AgentExecutionStore port on top of the row/DTO-level SqliteAgentExecutionStore
(Phase 1), translating to/from the ai_agent domain's AgentExecution/AIEnrichment.
"""

from __future__ import annotations

import json

from sentinel.ai_agent.domain.entities import AgentExecution, ExecutionLimits, ToolCallRecord
from sentinel.ai_agent.domain.value_objects import AIEnrichment
from sentinel.infrastructure.ai_agent.sqlite.agent_execution_store import (
    AgentExecutionCompletion,
    AgentExecutionStart,
    AiEnrichmentCreate,
    SqliteAgentExecutionStore,
)
from sentinel.shared.logging import get_logger
from sentinel.shared.retry import retry_best_effort_write

_logger = get_logger("ai_agent", "SqliteAgentExecutionStoreAdapter")


class SqliteAgentExecutionStoreAdapter:
    def __init__(self, store: SqliteAgentExecutionStore) -> None:
        self._store = store

    def start(self, execution: AgentExecution) -> None:
        retry_best_effort_write(
            lambda: self._store.start_execution(
                AgentExecutionStart(
                    id=execution.id,
                    subject_analysis_id=execution.subject_analysis_id,
                    correlation_id=execution.correlation_id,
                    agent_type=execution.agent_type,
                    execution_limits=json.dumps(
                        {
                            "maxDurationSeconds": execution.execution_limits.max_duration_seconds,
                            "maxToolCalls": execution.execution_limits.max_tool_calls,
                            "maxOutputSize": execution.execution_limits.max_output_size,
                        }
                    ),
                    started_at=execution.started_at,
                )
            ),
            logger=_logger, event="agent_execution_write",
            correlation_id=execution.correlation_id, analysis_id=execution.subject_analysis_id,
        )

    def complete(self, execution: AgentExecution) -> None:
        retry_best_effort_write(
            lambda: self._store.complete_execution(
                AgentExecutionCompletion(
                    id=execution.id,
                    status=execution.status,
                    tool_calls_log=json.dumps(
                        [{"toolName": c.tool_name, "calledAt": c.called_at, "resultSummary": c.result_summary} for c in execution.tool_calls_log]
                    ),
                    knowledge_base_entries_used=json.dumps(
                        [{"topic": t, "version": v} for t, v in execution.knowledge_base_entries_used]
                    ),
                    completed_at=execution.completed_at,
                )
            ),
            logger=_logger, event="agent_execution_write",
            correlation_id=execution.correlation_id, analysis_id=execution.subject_analysis_id,
        )

    def add_enrichment(self, enrichment: AIEnrichment) -> None:
        retry_best_effort_write(
            lambda: self._store.add_enrichment(
                AiEnrichmentCreate(
                    id=enrichment.id,
                    scope=enrichment.scope,
                    subject_id=enrichment.subject_id,
                    explanation=enrichment.explanation,
                    remediation_status=enrichment.remediation_status,
                    source_agent_execution_id=enrichment.source_agent_execution_id,
                    created_at=enrichment.created_at,
                    consequence_framing=enrichment.consequence_framing,
                    prioritization_hint=enrichment.prioritization_hint,
                    remediation_suggestion=enrichment.remediation_suggestion,
                    knowledge_base_entries_cited=(
                        json.dumps([{"topic": t, "version": v} for t, v in enrichment.knowledge_base_entries_cited])
                        if enrichment.knowledge_base_entries_cited
                        else None
                    ),
                )
            ),
            logger=_logger, event="ai_enrichment_write",
        )

    def get_enrichments_for_subject(self, subject_id: str) -> tuple[AIEnrichment, ...]:
        rows = self._store.get_enrichments_for_subject(subject_id)
        return tuple(self._enrichment_from_row(row) for row in rows)

    def get_latest_execution(self, subject_analysis_id: str) -> AgentExecution | None:
        rows = self._store.get_by_analysis_id(subject_analysis_id)
        if not rows:
            return None
        row = rows[-1]  # most recently started; SQLite returns insertion order for an unordered SELECT here
        limits = json.loads(row["execution_limits"])
        tool_calls = json.loads(row["tool_calls_log"])
        kb_used = json.loads(row["knowledge_base_entries_used"])
        return AgentExecution(
            id=row["id"],
            subject_analysis_id=row["subject_analysis_id"],
            correlation_id=row["correlation_id"],
            agent_type=row["agent_type"],
            execution_limits=ExecutionLimits(
                max_duration_seconds=limits.get("maxDurationSeconds", 0),
                max_tool_calls=limits.get("maxToolCalls", 0),
                max_output_size=limits.get("maxOutputSize", 0),
            ),
            started_at=row["started_at"],
            status=row["status"],
            tool_calls_log=[ToolCallRecord(tool_name=c["toolName"], called_at=c["calledAt"], result_summary=c["resultSummary"]) for c in tool_calls],
            knowledge_base_entries_used=[(e["topic"], e["version"]) for e in kb_used],
            completed_at=row["completed_at"],
        )

    @staticmethod
    def _enrichment_from_row(row) -> AIEnrichment:
        cited = json.loads(row["knowledge_base_entries_cited"]) if row["knowledge_base_entries_cited"] else []
        return AIEnrichment(
            id=row["id"], scope=row["scope"], subject_id=row["subject_id"],
            explanation=row["explanation"], remediation_status=row["remediation_status"],
            source_agent_execution_id=row["source_agent_execution_id"], created_at=row["created_at"],
            consequence_framing=row["consequence_framing"], prioritization_hint=row["prioritization_hint"],
            remediation_suggestion=row["remediation_suggestion"],
            knowledge_base_entries_cited=tuple((e["topic"], e["version"]) for e in cited),
        )
