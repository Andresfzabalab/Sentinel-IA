"""SecurityKnowledgeBaseCrossModuleAdapter -- implements ai_agent's
SecurityKnowledgeBasePort by reading the Security Intelligence & Data
Module's own store. Lives in infrastructure/ because infrastructure/ may
import from any module's domain/ and ports/ (Project_Structure.md) --
this is exactly the kind of cross-module wiring that belongs here, never
inside ai_agent/application/ or intelligence/application/ directly.
"""

from __future__ import annotations

from sentinel.ai_agent.ports.security_knowledge_base_port import KnowledgeBaseEntryView
from sentinel.intelligence.ports.knowledge_base_store import KnowledgeBaseStore


class SecurityKnowledgeBaseCrossModuleAdapter:
    def __init__(self, knowledge_base_store: KnowledgeBaseStore) -> None:
        self._store = knowledge_base_store

    def find_relevant(self, topic: str) -> KnowledgeBaseEntryView | None:
        entry = self._store.get_latest(topic)
        if entry is None:
            return None
        return KnowledgeBaseEntryView(topic=entry.topic, version=entry.version, content=entry.content)
