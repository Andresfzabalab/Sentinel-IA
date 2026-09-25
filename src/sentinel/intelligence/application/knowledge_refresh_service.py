"""Knowledge Refresh Service -- UC-8. An Application/Orchestration Service
(Domain_Services.md): schedules/executes calls to SecurityIntelligenceSourcePort
adapters, versions the results, writes them via KnowledgeBaseStore. Computes
no business rule -- it acquires, versions, and stores external data.

Runs on its own cycle, entirely independent of any Analysis
(Aggregates_and_Boundaries.md's Data Management Boundary) -- refreshing,
failing, or lagging here never affects a verdict.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sentinel.intelligence.domain.entities import SecurityKnowledgeBaseEntry
from sentinel.intelligence.domain.exceptions import DuplicateKnowledgeBaseEntry
from sentinel.intelligence.ports.knowledge_base_store import KnowledgeBaseStore
from sentinel.intelligence.ports.security_intelligence_source_port import SecurityIntelligenceSourcePort


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class KnowledgeRefreshService:
    def __init__(
        self, source: SecurityIntelligenceSourcePort, store: KnowledgeBaseStore, *, clock: "callable[[], str]" = _utc_now_iso
    ) -> None:
        self._source = source
        self._store = store
        self._clock = clock

    def refresh(self, topics: tuple[str, ...], *, id_factory: "callable[[str], str]") -> tuple[str, ...]:
        """Refreshes each topic independently -- one topic's source failure
        never blocks another's (mirrors P-09's per-scanner isolation spirit,
        applied to knowledge sources). Returns the topics actually updated.
        """
        updated: list[str] = []
        for topic in topics:
            content = self._source.fetch(topic)
            if content is None:
                continue  # this source has nothing for this topic -- not an error

            existing = self._store.get_latest(topic)
            next_version = 1 if existing is None else existing.version + 1
            if existing is not None and existing.content == content:
                continue  # unchanged -- publishing an identical version would be pure noise

            entry = SecurityKnowledgeBaseEntry(
                id=id_factory(topic), topic=topic, version=next_version,
                content=content, published_at=self._clock(),
            )
            try:
                self._store.publish(entry)
                updated.append(topic)
            except DuplicateKnowledgeBaseEntry:
                continue  # a concurrent refresh already published this version -- not an error

        return tuple(updated)
