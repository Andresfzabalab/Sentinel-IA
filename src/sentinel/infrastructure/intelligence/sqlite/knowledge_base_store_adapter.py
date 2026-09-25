"""SqliteKnowledgeBaseStoreAdapter -- implements the domain-facing
KnowledgeBaseStore port on top of the row-level SqliteKnowledgeBaseStore
(Phase 1), translating the infra-level DuplicateKnowledgeBaseEntry into
this module's own domain-level one (P-01/P-06-style boundary discipline,
same pattern as SqlitePolicyStoreAdapter).
"""

from __future__ import annotations

import uuid

from sentinel.infrastructure.intelligence.sqlite.knowledge_base_store import (
    DuplicateKnowledgeBaseEntry as SqliteDuplicateKnowledgeBaseEntry,
)
from sentinel.infrastructure.intelligence.sqlite.knowledge_base_store import (
    KnowledgeBaseEntryCreate,
    SqliteKnowledgeBaseStore,
)
from sentinel.intelligence.domain.entities import SecurityKnowledgeBaseEntry
from sentinel.intelligence.domain.exceptions import DuplicateKnowledgeBaseEntry
from sentinel.shared.logging import get_logger
from sentinel.shared.retry import retry_best_effort_write

_logger = get_logger("intelligence", "SqliteKnowledgeBaseStoreAdapter")


class SqliteKnowledgeBaseStoreAdapter:
    def __init__(self, store: SqliteKnowledgeBaseStore) -> None:
        self._store = store

    def publish(self, entry: SecurityKnowledgeBaseEntry) -> None:
        # DuplicateKnowledgeBaseEntry is a logic-level outcome, not a
        # transient infra failure -- it must propagate immediately,
        # unretried, so retry_best_effort_write only wraps the transient path.
        try:
            retry_best_effort_write(
                lambda: self._store.publish_entry(
                    KnowledgeBaseEntryCreate(
                        id=entry.id, topic=entry.topic, version=entry.version,
                        content=entry.content, source_reference=entry.source_reference, published_at=entry.published_at,
                    )
                ),
                logger=_logger, event="knowledge_base_write",
            )
        except SqliteDuplicateKnowledgeBaseEntry as exc:
            raise DuplicateKnowledgeBaseEntry(str(exc)) from exc

    def get_latest(self, topic: str) -> SecurityKnowledgeBaseEntry | None:
        row = self._store.get_latest_by_topic(topic)
        return self._to_domain(row) if row is not None else None

    def get(self, topic: str, version: int) -> SecurityKnowledgeBaseEntry | None:
        row = self._store.get_by_topic_and_version(topic, version)
        return self._to_domain(row) if row is not None else None

    @staticmethod
    def _to_domain(row) -> SecurityKnowledgeBaseEntry:
        return SecurityKnowledgeBaseEntry(
            id=row["id"], topic=row["topic"], version=row["version"],
            content=row["content"], source_reference=row["source_reference"], published_at=row["published_at"],
        )


def new_entry_id(topic: str) -> str:
    return f"{topic}-{uuid.uuid4()}"
