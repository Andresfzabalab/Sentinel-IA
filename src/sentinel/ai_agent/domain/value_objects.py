"""AI Enrichment -- advisory Value Object (docs/02_Domain/Entities_Value_Objects.md).

Structural exclusion, not a convention (P-02): this type has no field, at
any nesting level, capable of representing a verdict or a Security Score.
References the Finding/Analysis it explains via `subject_id` -- never the
reverse; a Finding holds no pointer to its own enrichment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Scope = Literal["finding", "analysis"]
RemediationStatus = Literal["provided", "insufficient_knowledge"]


@dataclass(frozen=True)
class AIEnrichment:
    id: str
    scope: Scope
    subject_id: str
    explanation: str
    remediation_status: RemediationStatus
    source_agent_execution_id: str
    created_at: str
    consequence_framing: str | None = None
    prioritization_hint: str | None = None
    remediation_suggestion: str | None = None
    knowledge_base_entries_cited: tuple[tuple[str, int], ...] = ()  # (topic, version) pairs
