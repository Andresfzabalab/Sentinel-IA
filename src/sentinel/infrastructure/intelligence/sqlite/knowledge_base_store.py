"""SqliteKnowledgeBaseStore -- implements KnowledgeBaseStore (T-Knowledge).

No relationship to any Analysis, Repository, or Policy -- consistent with
Aggregates_and_Boundaries.md's Data Management Boundary. Entries are
immutable once published; a refresh creates a new version, never edits an
old one.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


class DuplicateKnowledgeBaseEntry(RuntimeError):
    """Raised when a (topic, version) pair is published twice."""


@dataclass(frozen=True)
class KnowledgeBaseEntryCreate:
    id: str
    topic: str
    version: int
    content: str
    published_at: str
    source_reference: str | None = None


class SqliteKnowledgeBaseStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def publish_entry(self, entry: KnowledgeBaseEntryCreate) -> None:
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE;")
        try:
            try:
                conn.execute(
                    """
                    INSERT INTO security_knowledge_base_entry (
                        id, topic, version, content, source_reference, published_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (entry.id, entry.topic, entry.version, entry.content, entry.source_reference, entry.published_at),
                )
            except sqlite3.IntegrityError as exc:
                conn.execute("ROLLBACK;")
                raise DuplicateKnowledgeBaseEntry(
                    f"topic={entry.topic!r} version={entry.version!r} already published"
                ) from exc
            conn.execute("COMMIT;")
        except DuplicateKnowledgeBaseEntry:
            raise
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    def get_by_topic_and_version(self, topic: str, version: int) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM security_knowledge_base_entry WHERE topic = ? AND version = ?", (topic, version)
        ).fetchone()

    def get_latest_by_topic(self, topic: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM security_knowledge_base_entry WHERE topic = ? ORDER BY version DESC LIMIT 1",
            (topic,),
        ).fetchone()
