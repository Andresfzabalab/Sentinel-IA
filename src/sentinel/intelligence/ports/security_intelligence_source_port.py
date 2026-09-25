"""SecurityIntelligenceSourcePort -- one adapter per external feed/CVE
source (Adapter pattern, mirroring ScannerPort). The exact external
source(s) are explicitly left open by AI_Agent_Architecture.md §11
("an implementation and research concern, not an architectural one") --
this port's shape is what any future real feed adapter must satisfy.
"""

from __future__ import annotations

from typing import Protocol


class SecurityIntelligenceSourcePort(Protocol):
    def fetch(self, topic: str) -> str | None:
        """Returns raw remediation/security content for a topic, or None
        if this source has nothing for it -- never fabricated content.
        """
        ...
