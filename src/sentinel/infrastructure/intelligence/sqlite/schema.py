"""Security Intelligence & Data Module's own store: security_knowledge_base_entry.

No relationship to any Analysis, Repository, or Policy -- no FK, no
analysis_id column, no correlation_id column (Aggregates_and_Boundaries.md's
Data Management Boundary).
"""

from __future__ import annotations

import sqlite3

CREATE_SECURITY_KNOWLEDGE_BASE_ENTRY = """
CREATE TABLE IF NOT EXISTS security_knowledge_base_entry (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    source_reference TEXT NULL,
    published_at TEXT NOT NULL,
    UNIQUE (topic, version)
);
"""

ALL_TABLES_IN_ORDER: tuple[str, ...] = (CREATE_SECURITY_KNOWLEDGE_BASE_ENTRY,)

DROP_TABLES_IN_ORDER: tuple[str, ...] = ("DROP TABLE IF EXISTS security_knowledge_base_entry;",)


def create_intelligence_schema(conn: sqlite3.Connection) -> None:
    for statement in ALL_TABLES_IN_ORDER:
        conn.execute(statement)


def drop_intelligence_schema(conn: sqlite3.Connection) -> None:
    for statement in DROP_TABLES_IN_ORDER:
        conn.execute(statement)
