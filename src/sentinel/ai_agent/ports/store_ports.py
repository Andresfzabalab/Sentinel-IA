"""AgentExecutionStore (this module's own persistence) and AuditRecorderPort
(the one documented write exception among Cross-Module Ports, restricted to
Audit Records only -- Ports_and_Interfaces.md).
"""

from __future__ import annotations

from typing import Protocol

from sentinel.ai_agent.domain.entities import AgentExecution
from sentinel.ai_agent.domain.value_objects import AIEnrichment
from sentinel.core.domain.audit.entities import AuditRecord


class AgentExecutionStore(Protocol):
    def start(self, execution: AgentExecution) -> None: ...

    def complete(self, execution: AgentExecution) -> None: ...

    def add_enrichment(self, enrichment: AIEnrichment) -> None: ...

    def get_enrichments_for_subject(self, subject_id: str) -> tuple[AIEnrichment, ...]: ...

    def get_latest_execution(self, subject_analysis_id: str) -> AgentExecution | None: ...


class AuditRecorderPort(Protocol):
    """Write-restricted to Audit Records only -- this port has no method
    that could touch `Analysis`, `Finding`, `Policy`, or any verdict-bearing
    state, not even for reading (Ports_and_Interfaces.md's "The One Write
    Exception"). Structurally identical in shape to Sentinel Core's own
    `AuditStore.append` -- the same concrete adapter instance satisfies
    both Protocols, wired once in composition.py.
    """

    def append(self, record: AuditRecord) -> None: ...
