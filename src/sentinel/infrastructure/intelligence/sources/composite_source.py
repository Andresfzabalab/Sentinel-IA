"""CompositeSecurityIntelligenceSource -- queries an ordered list of
SecurityIntelligenceSourcePort adapters for the same topic and concatenates
every non-None result into one combined document. Lets KnowledgeRefreshService
(which takes exactly one source) still be enriched from multiple real
origins (StaticSeedSource's curated baseline + MitreCweSource + CisaKevSource)
without changing its interface. One source's failure never hides another's
content -- each is queried independently.
"""

from __future__ import annotations

from sentinel.intelligence.ports.security_intelligence_source_port import SecurityIntelligenceSourcePort


class CompositeSecurityIntelligenceSource:
    def __init__(self, sources: tuple[SecurityIntelligenceSourcePort, ...]) -> None:
        self._sources = sources

    def fetch(self, topic: str) -> str | None:
        sections = [content for source in self._sources if (content := source.fetch(topic)) is not None]
        if not sections:
            return None
        return "\n\n".join(sections)
