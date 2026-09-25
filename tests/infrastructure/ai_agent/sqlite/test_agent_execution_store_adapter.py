"""Proves SqliteAgentExecutionStoreAdapter's domain<->DTO round trip: an
AgentExecution/AIEnrichment written through the adapter comes back as an
equivalent domain object, including JSON-serialized tool_calls_log and
knowledge_base_entries_used.
"""

from __future__ import annotations

from sentinel.ai_agent.domain.entities import AgentExecution, ExecutionLimits, ToolCallRecord
from sentinel.ai_agent.domain.value_objects import AIEnrichment
from sentinel.infrastructure.ai_agent.sqlite.agent_execution_store import SqliteAgentExecutionStore
from sentinel.infrastructure.ai_agent.sqlite.agent_execution_store_adapter import SqliteAgentExecutionStoreAdapter


def _adapter(sqlite_conn) -> SqliteAgentExecutionStoreAdapter:
    return SqliteAgentExecutionStoreAdapter(SqliteAgentExecutionStore(sqlite_conn))


def test_start_and_get_latest_execution_round_trip(sqlite_conn) -> None:
    adapter = _adapter(sqlite_conn)
    execution = AgentExecution(
        id="ae-1", subject_analysis_id="an-1", correlation_id="corr-1", agent_type="security-investigation",
        execution_limits=ExecutionLimits(max_duration_seconds=30, max_tool_calls=10, max_output_size=1000),
        started_at="t0",
    )

    adapter.start(execution)
    loaded = adapter.get_latest_execution("an-1")

    assert loaded is not None
    assert loaded.id == "ae-1"
    assert loaded.status == "running"
    assert loaded.execution_limits == ExecutionLimits(max_duration_seconds=30, max_tool_calls=10, max_output_size=1000)


def test_complete_persists_tool_calls_and_kb_entries_used(sqlite_conn) -> None:
    adapter = _adapter(sqlite_conn)
    execution = AgentExecution(
        id="ae-2", subject_analysis_id="an-2", correlation_id="corr-2", agent_type="security-investigation",
        execution_limits=ExecutionLimits(max_duration_seconds=30, max_tool_calls=10, max_output_size=1000),
        started_at="t0",
    )
    adapter.start(execution)

    execution.tool_calls_log = [ToolCallRecord(tool_name="ReadFindingsTool", called_at="t0", result_summary="()")]
    execution.knowledge_base_entries_used = [("sast", 1)]
    execution.complete("t1")
    adapter.complete(execution)

    loaded = adapter.get_latest_execution("an-2")
    assert loaded.status == "completed"
    assert loaded.completed_at == "t1"
    assert loaded.tool_calls_log == [ToolCallRecord(tool_name="ReadFindingsTool", called_at="t0", result_summary="()")]
    assert loaded.knowledge_base_entries_used == [("sast", 1)]


def test_add_enrichment_and_get_enrichments_for_subject_round_trip(sqlite_conn) -> None:
    adapter = _adapter(sqlite_conn)
    adapter.start(
        AgentExecution(
            id="ae-1", subject_analysis_id="an-1", correlation_id="corr-1", agent_type="security-investigation",
            execution_limits=ExecutionLimits(max_duration_seconds=30, max_tool_calls=10, max_output_size=1000),
            started_at="t0",
        )
    )
    enrichment = AIEnrichment(
        id="enr-1", scope="finding", subject_id="f-1", explanation="explanation text",
        remediation_status="provided", source_agent_execution_id="ae-1", created_at="t1",
        consequence_framing="framing", prioritization_hint="hint", remediation_suggestion="fix it",
        knowledge_base_entries_cited=(("sast", 2),),
    )

    adapter.add_enrichment(enrichment)
    loaded = adapter.get_enrichments_for_subject("f-1")

    assert len(loaded) == 1
    assert loaded[0] == enrichment


def test_get_latest_execution_returns_none_when_no_execution_exists(sqlite_conn) -> None:
    adapter = _adapter(sqlite_conn)

    assert adapter.get_latest_execution("an-missing") is None
