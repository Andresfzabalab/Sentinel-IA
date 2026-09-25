"""Proves SecurityKnowledgeBaseCrossModuleAdapter reads through to the
Security Intelligence & Data Module's own store (Module_Boundaries.md's
cross-module wiring, done in infrastructure/).
"""

from __future__ import annotations

from sentinel.infrastructure.ai_agent.security_knowledge_base_adapter import (
    SecurityKnowledgeBaseCrossModuleAdapter,
)
from sentinel.infrastructure.intelligence.sqlite.knowledge_base_store import SqliteKnowledgeBaseStore
from sentinel.infrastructure.intelligence.sqlite.knowledge_base_store_adapter import (
    SqliteKnowledgeBaseStoreAdapter,
)
from sentinel.intelligence.domain.entities import SecurityKnowledgeBaseEntry


def test_find_relevant_returns_the_latest_entry_for_a_topic(sqlite_conn) -> None:
    store_adapter = SqliteKnowledgeBaseStoreAdapter(SqliteKnowledgeBaseStore(sqlite_conn))
    store_adapter.publish(SecurityKnowledgeBaseEntry(id="sast-1", topic="sast", version=1, content="v1 content", published_at="t0"))
    store_adapter.publish(SecurityKnowledgeBaseEntry(id="sast-2", topic="sast", version=2, content="v2 content", published_at="t1"))
    adapter = SecurityKnowledgeBaseCrossModuleAdapter(store_adapter)

    entry = adapter.find_relevant("sast")

    assert entry is not None
    assert entry.version == 2
    assert entry.content == "v2 content"


def test_find_relevant_returns_none_for_an_unknown_topic(sqlite_conn) -> None:
    store_adapter = SqliteKnowledgeBaseStoreAdapter(SqliteKnowledgeBaseStore(sqlite_conn))
    adapter = SecurityKnowledgeBaseCrossModuleAdapter(store_adapter)

    assert adapter.find_relevant("does-not-exist") is None
