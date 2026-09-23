"""AI & Agent Module's own SQLite tables (agent_execution, ai_enrichment).

Per docs/03_API/Data_Model.md's physical-layout rule: `agent_execution.subject_analysis_id`
and `ai_enrichment.subject_id` reference core's `analysis`/`finding` tables
*by value only* -- deliberately no FOREIGN KEY clause, since a DB-level
constraint would physically couple two modules' schemas. The one FK that
*is* enforced here (`ai_enrichment.source_agent_execution_id`) stays inside
this module's own store.
"""

from __future__ import annotations

import sqlite3

CREATE_AGENT_EXECUTION = """
CREATE TABLE IF NOT EXISTS agent_execution (
    id TEXT PRIMARY KEY,
    subject_analysis_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    agent_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'pending_unavailable')),
    tool_calls_log TEXT NOT NULL,
    knowledge_base_entries_used TEXT NOT NULL,
    execution_limits TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT NULL
);
"""

CREATE_AI_ENRICHMENT = """
CREATE TABLE IF NOT EXISTS ai_enrichment (
    id TEXT PRIMARY KEY,
    scope TEXT NOT NULL CHECK (scope IN ('finding', 'analysis')),
    subject_id TEXT NOT NULL,
    explanation TEXT NOT NULL,
    consequence_framing TEXT NULL,
    prioritization_hint TEXT NULL,
    remediation_suggestion TEXT NULL,
    remediation_status TEXT NOT NULL CHECK (remediation_status IN ('provided', 'insufficient_knowledge')),
    knowledge_base_entries_cited TEXT NULL,
    source_agent_execution_id TEXT NOT NULL REFERENCES agent_execution(id),
    created_at TEXT NOT NULL
);
"""

ALL_TABLES_IN_ORDER: tuple[str, ...] = (
    CREATE_AGENT_EXECUTION,
    CREATE_AI_ENRICHMENT,
)

DROP_TABLES_IN_ORDER: tuple[str, ...] = (
    "DROP TABLE IF EXISTS ai_enrichment;",
    "DROP TABLE IF EXISTS agent_execution;",
)


def create_ai_agent_schema(conn: sqlite3.Connection) -> None:
    for statement in ALL_TABLES_IN_ORDER:
        conn.execute(statement)


def drop_ai_agent_schema(conn: sqlite3.Connection) -> None:
    for statement in DROP_TABLES_IN_ORDER:
        conn.execute(statement)
