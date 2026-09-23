"""SqliteAuditStore -- implements AuditStore (T-Audit).

Append-only: no method in this class issues an UPDATE or DELETE against
`audit_record`, by construction -- there is no method that would let one.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class AuditRecordCreate:
    id: str
    actor: str
    event_type: str
    origin: str  # 'scanner' | 'sentinel-core' | 'llm-agent'
    payload: str  # JSON
    created_at: str
    subject_analysis_id: str | None = None
    correlation_id: str | None = None


class SqliteAuditStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def append(self, record: AuditRecordCreate) -> None:
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE;")
        try:
            conn.execute(
                """
                INSERT INTO audit_record (
                    id, subject_analysis_id, correlation_id, actor, event_type, origin, payload, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.subject_analysis_id,
                    record.correlation_id,
                    record.actor,
                    record.event_type,
                    record.origin,
                    record.payload,
                    record.created_at,
                ),
            )
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    def get_by_analysis_id(self, analysis_id: str) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM audit_record WHERE subject_analysis_id = ? ORDER BY created_at", (analysis_id,)
        ).fetchall()

    def get_by_correlation_id(self, correlation_id: str) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM audit_record WHERE correlation_id = ? ORDER BY created_at", (correlation_id,)
        ).fetchall()
