"""SQLite connection factory shared by every *Store adapter.

Per docs/03_API/Persistence_Strategy.md's Concurrency Model: WAL mode is
enabled so DevSecOps reads (UC-5, UC-6) are never blocked by an in-progress
Analysis write. `foreign_keys = ON` enforces the intra-module FK
constraints declared in schema.py (Data_Model.md's within-module FKs);
cross-module references (agent_execution.subject_analysis_id,
ai_enrichment.subject_id) simply have no FOREIGN KEY clause at all, so this
pragma has no effect on them one way or the other.

`isolation_level=None` puts the connection in autocommit mode so every
store issues its own explicit `BEGIN IMMEDIATE ... COMMIT` block, matching
Persistence_Strategy.md's transaction pseudocode exactly -- sqlite3's
implicit transaction management is not used here.
"""

from __future__ import annotations

import sqlite3


def connect(database_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(database_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn
