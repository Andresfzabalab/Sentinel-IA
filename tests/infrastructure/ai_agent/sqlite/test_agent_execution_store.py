"""Proves the AI & Agent Module's own store, including the absence of any
cross-module foreign key into Sentinel Core's tables (Data_Model.md's
physical-layout rule) -- a query against agent_execution/ai_enrichment
never requires or exercises a foreign key into analysis/finding, because
there isn't one, by design.
"""

from __future__ import annotations

from sentinel.infrastructure.ai_agent.sqlite.agent_execution_store import (
    AgentExecutionCompletion,
    AgentExecutionStart,
    AiEnrichmentCreate,
    SqliteAgentExecutionStore,
)


def test_start_execution_succeeds_even_when_the_referenced_analysis_does_not_exist(sqlite_conn):
    """This is the direct proof of 'no FK crosses the module boundary': if a
    FOREIGN KEY existed on subject_analysis_id, this insert would fail with
    an IntegrityError even though PRAGMA foreign_keys=ON is set on this
    connection (connection.py) -- it doesn't, because no such constraint
    was ever declared (Data_Model.md's physical-layout rule).
    """
    store = SqliteAgentExecutionStore(sqlite_conn)

    store.start_execution(
        AgentExecutionStart(
            id="agent-exec-1",
            subject_analysis_id="an-does-not-exist",
            correlation_id="corr-1",
            agent_type="security-investigation",
            execution_limits='{"maxDurationSeconds": 30, "maxToolCalls": 10, "maxOutputSize": 4096}',
            started_at="t0",
        )
    )

    rows = store.get_by_analysis_id("an-does-not-exist")
    assert len(rows) == 1
    assert rows[0]["status"] == "running"


def test_complete_execution_and_add_enrichment(sqlite_conn):
    store = SqliteAgentExecutionStore(sqlite_conn)
    store.start_execution(
        AgentExecutionStart(
            id="agent-exec-1",
            subject_analysis_id="an-1",
            correlation_id="corr-1",
            agent_type="security-investigation",
            execution_limits="{}",
            started_at="t0",
        )
    )

    store.complete_execution(
        AgentExecutionCompletion(
            id="agent-exec-1",
            status="completed",
            tool_calls_log='[{"toolName": "ReadFindingsTool", "calledAt": "t0"}]',
            knowledge_base_entries_used='[{"topic": "sql-injection", "version": 1}]',
            completed_at="t1",
        )
    )

    store.add_enrichment(
        AiEnrichmentCreate(
            id="enrich-1",
            scope="finding",
            subject_id="f-1",  # a Finding id, by value only -- no FK
            explanation="This is a SQL injection risk because...",
            remediation_status="provided",
            source_agent_execution_id="agent-exec-1",
            created_at="t1",
            remediation_suggestion="Use parameterized queries.",
        )
    )

    execution = store.get_by_analysis_id("an-1")[0]
    assert execution["status"] == "completed"
    enrichments = store.get_enrichments_for_subject("f-1")
    assert len(enrichments) == 1
    assert enrichments[0]["remediation_status"] == "provided"


def test_pending_unavailable_never_sets_completed_at():
    completion = AgentExecutionCompletion(
        id="agent-exec-1",
        status="pending_unavailable",
        tool_calls_log="[]",
        knowledge_base_entries_used="[]",
    )
    assert completion.completed_at is None
