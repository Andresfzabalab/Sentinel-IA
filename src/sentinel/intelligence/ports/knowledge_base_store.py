"""KnowledgeBaseStore -- this module's own persistence port
(Ports_and_Interfaces.md). Domain-object in, domain-object out."""

from __future__ import annotations

from typing import Protocol

from sentinel.intelligence.domain.entities import SecurityKnowledgeBaseEntry


class KnowledgeBaseStore(Protocol):
    def publish(self, entry: SecurityKnowledgeBaseEntry) -> None:
        """Raises DuplicateKnowledgeBaseEntry (core/domain/exceptions.py-style,
        defined locally here since this module owns this concept) if
        (topic, version) was already published.
        """
        ...

    def get_latest(self, topic: str) -> SecurityKnowledgeBaseEntry | None: ...

    def get(self, topic: str, version: int) -> SecurityKnowledgeBaseEntry | None: ...
