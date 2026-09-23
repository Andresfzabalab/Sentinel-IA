"""SqliteNotificationStore -- implements NotificationStore (T-Notify).

A failed delivery is a new row on retry, never an edit of the failed one
(Entities_Value_Objects.md's Notification lifecycle) -- there is no update
method here, only `record_attempt`, called once per attempt.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class NotificationAttempt:
    id: str
    analysis_id: str
    channel: str
    status: str  # 'pending' | 'delivered' | 'failed'
    attempted_at: str
    content_snapshot: str | None = None


class SqliteNotificationStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def record_attempt(self, attempt: NotificationAttempt) -> None:
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE;")
        try:
            conn.execute(
                """
                INSERT INTO notification (id, analysis_id, channel, status, attempted_at, content_snapshot)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt.id,
                    attempt.analysis_id,
                    attempt.channel,
                    attempt.status,
                    attempt.attempted_at,
                    attempt.content_snapshot,
                ),
            )
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    def get_by_analysis_id(self, analysis_id: str) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM notification WHERE analysis_id = ? ORDER BY attempted_at", (analysis_id,)
        ).fetchall()
