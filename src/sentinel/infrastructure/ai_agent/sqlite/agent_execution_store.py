"""SqliteAgentExecutionStore -- implements AgentExecutionStore (T-Agent).

Touches only `agent_execution` and `ai_enrichment` -- the AI & Agent
Module's own tables. `subject_analysis_id` and `ai_enrichment.subject_id`
are cross-module references *by value only*, with no FOREIGN KEY
constraint (Data_Model.md's physical-layout rule) -- this store never
queries `analysis` or `finding` directly.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentExecutionStart:
    id: str
    subject_analysis_id: str
    correlation_id: str
    agent_type: str
    execution_limits: str  # JSON: {maxDurationSeconds, maxToolCalls, maxOutputSize}
    started_at: str


@dataclass(frozen=True)
class AgentExecutionCompletion:
    id: str
    status: str  # 'completed' | 'pending_unavailable'
    tool_calls_log: str  # JSON array
    knowledge_base_entries_used: str  # JSON array of {topic, version}
    completed_at: str | None = None  # None while still 'pending_unavailable'


@dataclass(frozen=True)
class AiEnrichmentCreate:
    id: str
    scope: str  # 'finding' | 'analysis'
    subject_id: str  # a findingId or analysisId, by value only
    explanation: str
    remediation_status: str  # 'provided' | 'insufficient_knowledge'
    source_agent_execution_id: str
    created_at: str
    consequence_framing: str | None = None
    prioritization_hint: str | None = None
    remediation_suggestion: str | None = None
    knowledge_base_entries_cited: str | None = None  # JSON array of {topic, version}


class SqliteAgentExecutionStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def start_execution(self, start: AgentExecutionStart) -> None:
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE;")
        try:
            conn.execute(
                """
                INSERT INTO agent_execution (
                    id, subject_analysis_id, correlation_id, agent_type, status,
                    tool_calls_log, knowledge_base_entries_used, execution_limits, started_at
                ) VALUES (?, ?, ?, ?, 'running', '[]', '[]', ?, ?)
                """,
                (start.id, start.subject_analysis_id, start.correlation_id, start.agent_type,
                 start.execution_limits, start.started_at),
            )
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    def complete_execution(self, completion: AgentExecutionCompletion) -> None:
        """T-Agent -- Execution Recorded. Never touches Analysis, Finding, or Policy state."""
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE;")
        try:
            conn.execute(
                """
                UPDATE agent_execution
                SET status = ?, tool_calls_log = ?, knowledge_base_entries_used = ?, completed_at = ?
                WHERE id = ?
                """,
                (
                    completion.status,
                    completion.tool_calls_log,
                    completion.knowledge_base_entries_used,
                    completion.completed_at,
                    completion.id,
                ),
            )
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    def add_enrichment(self, enrichment: AiEnrichmentCreate) -> None:
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE;")
        try:
            conn.execute(
                """
                INSERT INTO ai_enrichment (
                    id, scope, subject_id, explanation, consequence_framing, prioritization_hint,
                    remediation_suggestion, remediation_status, knowledge_base_entries_cited,
                    source_agent_execution_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    enrichment.id,
                    enrichment.scope,
                    enrichment.subject_id,
                    enrichment.explanation,
                    enrichment.consequence_framing,
                    enrichment.prioritization_hint,
                    enrichment.remediation_suggestion,
                    enrichment.remediation_status,
                    enrichment.knowledge_base_entries_cited,
                    enrichment.source_agent_execution_id,
                    enrichment.created_at,
                ),
            )
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    def get_by_analysis_id(self, subject_analysis_id: str) -> list[sqlite3.Row]:
        """Queried by value, per Observability_and_Logging.md's diagnostic
        assembly -- there is no database-enforced relationship to join on.
        """
        return self._conn.execute(
            "SELECT * FROM agent_execution WHERE subject_analysis_id = ?", (subject_analysis_id,)
        ).fetchall()

    def get_enrichments_for_subject(self, subject_id: str) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM ai_enrichment WHERE subject_id = ?", (subject_id,)
        ).fetchall()
