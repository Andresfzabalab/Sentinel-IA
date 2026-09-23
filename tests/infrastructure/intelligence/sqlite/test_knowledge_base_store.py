"""Proves Security Knowledge Base entries are versioned, immutable, and
have no relationship to any Analysis/Repository/Policy (Aggregates_and_Boundaries.md's
Data Management Boundary)."""

from __future__ import annotations

import pytest

from sentinel.infrastructure.intelligence.sqlite.knowledge_base_store import (
    DuplicateKnowledgeBaseEntry,
    KnowledgeBaseEntryCreate,
    SqliteKnowledgeBaseStore,
)


def test_publish_and_read_back(sqlite_conn):
    store = SqliteKnowledgeBaseStore(sqlite_conn)

    store.publish_entry(
        KnowledgeBaseEntryCreate(id="kb-1", topic="sql-injection", version=1, content="Use parameterized queries.", published_at="t0")
    )

    entry = store.get_by_topic_and_version("sql-injection", 1)
    assert entry["content"] == "Use parameterized queries."


def test_a_refresh_creates_a_new_version_never_edits_the_old_one(sqlite_conn):
    store = SqliteKnowledgeBaseStore(sqlite_conn)
    store.publish_entry(KnowledgeBaseEntryCreate(id="kb-1", topic="xss", version=1, content="v1 guidance", published_at="t0"))
    store.publish_entry(KnowledgeBaseEntryCreate(id="kb-2", topic="xss", version=2, content="v2 guidance", published_at="t1"))

    assert store.get_by_topic_and_version("xss", 1)["content"] == "v1 guidance"
    assert store.get_latest_by_topic("xss")["content"] == "v2 guidance"


def test_rejects_publishing_the_same_topic_and_version_twice(sqlite_conn):
    store = SqliteKnowledgeBaseStore(sqlite_conn)
    store.publish_entry(KnowledgeBaseEntryCreate(id="kb-1", topic="xss", version=1, content="v1", published_at="t0"))

    with pytest.raises(DuplicateKnowledgeBaseEntry):
        store.publish_entry(KnowledgeBaseEntryCreate(id="kb-1-dup", topic="xss", version=1, content="different content", published_at="t1"))
