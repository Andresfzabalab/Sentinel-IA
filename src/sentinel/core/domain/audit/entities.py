"""AuditRecord -- immutable after creation.

Frozen by construction: there is no method on this class that mutates a
field once set (Entities_Value_Objects.md: "once written, never updated or
deleted").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

AuditOrigin = Literal["scanner", "sentinel-core", "llm-agent"]


@dataclass(frozen=True)
class AuditRecord:
    id: str
    actor: str
    event_type: str
    origin: AuditOrigin
    payload: dict[str, Any]
    created_at: str
    subject_analysis_id: str | None = None
    correlation_id: str | None = None
