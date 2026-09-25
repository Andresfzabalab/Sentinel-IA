"""Proves CompositeSecurityIntelligenceSource: concatenates every source's
non-None content for a topic, and returns None only when every source
returns None -- one source's absence never hides another's content.
"""

from __future__ import annotations

from sentinel.infrastructure.intelligence.sources.composite_source import (
    CompositeSecurityIntelligenceSource,
)


class FakeSource:
    def __init__(self, content: dict[str, str | None]) -> None:
        self._content = content

    def fetch(self, topic: str) -> str | None:
        return self._content.get(topic)


def test_concatenates_content_from_every_source_that_has_something() -> None:
    composite = CompositeSecurityIntelligenceSource(
        (FakeSource({"sast": "baseline guidance"}), FakeSource({"sast": "CWE detail"}))
    )

    content = composite.fetch("sast")

    assert content == "baseline guidance\n\nCWE detail"


def test_skips_sources_with_nothing_for_the_topic() -> None:
    composite = CompositeSecurityIntelligenceSource((FakeSource({}), FakeSource({"sast": "only this one"})))

    assert composite.fetch("sast") == "only this one"


def test_returns_none_when_every_source_has_nothing() -> None:
    composite = CompositeSecurityIntelligenceSource((FakeSource({}), FakeSource({})))

    assert composite.fetch("sast") is None
