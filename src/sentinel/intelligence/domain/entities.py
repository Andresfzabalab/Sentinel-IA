"""SecurityKnowledgeBaseEntry -- a data/knowledge concept, not a domain
Aggregate (Aggregates_and_Boundaries.md's Data Management Boundary). No
relationship to any Analysis, Repository, or Policy.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SecurityKnowledgeBaseEntry:
    id: str
    topic: str
    version: int
    content: str
    published_at: str
    source_reference: str | None = None
