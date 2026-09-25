"""Proves the Knowledge Refresh Service (UC-8): versions new content,
skips unchanged content (no publish noise), and isolates one topic's
source failure from another's -- against a fake source/store, since the
real StaticSeedSource has no failure mode of its own to simulate.
"""

from __future__ import annotations

from sentinel.intelligence.application.knowledge_refresh_service import KnowledgeRefreshService
from sentinel.intelligence.domain.entities import SecurityKnowledgeBaseEntry
from sentinel.intelligence.domain.exceptions import DuplicateKnowledgeBaseEntry


class FakeSource:
    def __init__(self, content: dict[str, str | None]) -> None:
        self._content = content

    def fetch(self, topic: str) -> str | None:
        return self._content.get(topic)


class FakeStore:
    def __init__(self) -> None:
        self._entries: dict[str, SecurityKnowledgeBaseEntry] = {}
        self.published: list[SecurityKnowledgeBaseEntry] = []

    def publish(self, entry: SecurityKnowledgeBaseEntry) -> None:
        if entry.topic in self._entries and self._entries[entry.topic].version == entry.version:
            raise DuplicateKnowledgeBaseEntry(f"{entry.topic} v{entry.version} already exists")
        self._entries[entry.topic] = entry
        self.published.append(entry)

    def get_latest(self, topic: str) -> SecurityKnowledgeBaseEntry | None:
        return self._entries.get(topic)

    def get(self, topic: str, version: int) -> SecurityKnowledgeBaseEntry | None:
        entry = self._entries.get(topic)
        return entry if entry is not None and entry.version == version else None


def test_first_refresh_publishes_version_1_for_every_topic_with_content() -> None:
    source = FakeSource({"sast": "sast guidance", "secret": None})
    store = FakeStore()
    service = KnowledgeRefreshService(source, store, clock=lambda: "t0")

    updated = service.refresh(("sast", "secret"), id_factory=lambda topic: f"{topic}-1")

    assert updated == ("sast",)  # "secret" had no content this run -- not an error
    assert store.get_latest("sast").version == 1


def test_refreshing_unchanged_content_is_a_noop() -> None:
    source = FakeSource({"sast": "same content"})
    store = FakeStore()
    service = KnowledgeRefreshService(source, store, clock=lambda: "t0")
    service.refresh(("sast",), id_factory=lambda topic: f"{topic}-1")

    updated = service.refresh(("sast",), id_factory=lambda topic: f"{topic}-2")

    assert updated == ()
    assert store.get_latest("sast").version == 1


def test_changed_content_publishes_the_next_version() -> None:
    source = FakeSource({"sast": "v1 content"})
    store = FakeStore()
    service = KnowledgeRefreshService(source, store, clock=lambda: "t0")
    service.refresh(("sast",), id_factory=lambda topic: f"{topic}-1")

    source._content["sast"] = "v2 content"
    updated = service.refresh(("sast",), id_factory=lambda topic: f"{topic}-2")

    assert updated == ("sast",)
    assert store.get_latest("sast").version == 2
    assert store.get_latest("sast").content == "v2 content"


class _AlwaysDuplicateStore(FakeStore):
    """Simulates another process winning the race to publish the same
    next version -- publish() always raises, no matter what's passed.
    """

    def publish(self, entry: SecurityKnowledgeBaseEntry) -> None:
        raise DuplicateKnowledgeBaseEntry(f"{entry.topic} v{entry.version} already exists")


def test_a_concurrent_duplicate_publish_is_treated_as_a_noop_not_an_error() -> None:
    store = _AlwaysDuplicateStore()
    store._entries["sast"] = SecurityKnowledgeBaseEntry(id="sast-1", topic="sast", version=1, content="v1", published_at="t0")
    source = FakeSource({"sast": "v2 content"})
    service = KnowledgeRefreshService(source, store, clock=lambda: "t1")

    updated = service.refresh(("sast",), id_factory=lambda topic: f"{topic}-2")

    assert updated == ()
