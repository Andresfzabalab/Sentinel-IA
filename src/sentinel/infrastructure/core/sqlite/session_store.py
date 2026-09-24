"""SqliteSessionStore -- DevSecOps API session tokens (Phase 8).

Kept deliberately raw/row-level, like the other *Store classes -- Session
is not a domain Aggregate (the MVP's Identity context is intentionally
minimal), so there is no domain-facing adapter here. interfaces/http/ is
allowed to use this directly (Project_Structure.md: interfaces/ may import
from any module's infrastructure/).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class SessionCreate:
    token: str
    devsecops_login: str
    created_at: str
    expires_at: str


class SqliteSessionStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create_session(self, session: SessionCreate) -> None:
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE;")
        try:
            conn.execute(
                "INSERT INTO session (token, devsecops_login, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (session.token, session.devsecops_login, session.created_at, session.expires_at),
            )
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    def get_session(self, token: str) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM session WHERE token = ?", (token,)).fetchone()

    def delete_session(self, token: str) -> None:
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE;")
        try:
            conn.execute("DELETE FROM session WHERE token = ?", (token,))
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise
