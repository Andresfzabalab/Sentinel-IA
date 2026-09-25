"""SecurityKnowledgeBasePort -- Cross-Module, read-only
(docs/02_Domain/Ports_and_Interfaces.md). Declared here for the same
dependency-direction reason as SecurityResultQueryPort: ai_agent/application/
depends on its own module's ports/, never on intelligence/ directly. The
Security Intelligence & Data Module provides the concrete implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class KnowledgeBaseEntryView:
    topic: str
    version: int
    content: str


class SecurityKnowledgeBasePort(Protocol):
    def find_relevant(self, topic: str) -> KnowledgeBaseEntryView | None:
        """Returns None -- an explicit "no sufficient knowledge" result --
        rather than ever fabricating content (AI_Agent_Architecture.md §6's
        bounded-honesty rule). No write method exists on this port.
        """
        ...
