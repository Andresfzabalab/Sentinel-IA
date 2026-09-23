"""Persistence port interfaces the Analysis Orchestrator depends on --
domain-object in, domain-object out. Per Project_Structure.md's import
direction rule, core/application/ (the Orchestrator) may depend on these
interfaces but never on a concrete `infrastructure/` class directly; the
concrete SQLite-backed adapters that implement these Protocols live under
infrastructure/core/sqlite/*_adapter.py.

Naming follows Ports_and_Interfaces.md: persistence ports are `*Store`,
never `Repository` (that word is reserved for the domain concept).
"""

from __future__ import annotations

from typing import Protocol

from sentinel.core.domain.analysis.entities import Analysis, Finding, ScannerExecution
from sentinel.core.domain.audit.entities import AuditRecord
from sentinel.core.domain.notification.entities import Notification
from sentinel.core.domain.policy.value_objects import PolicyVersion
from sentinel.core.domain.repository.entities import Repository


class AnalysisStore(Protocol):
    def find_existing_id(self, correlation_id: str) -> str | None: ...

    def create_or_get(self, analysis: Analysis) -> str: ...

    def create_failed(self, analysis: Analysis) -> str: ...

    def complete_scanner_execution(
        self, analysis_id: str, execution: ScannerExecution, findings: tuple[Finding, ...]
    ) -> None: ...

    def finalize(self, analysis: Analysis) -> None: ...


class RepositoryConfigStore(Protocol):
    def get_repository(self, repository_id: str) -> Repository: ...


class PolicyStore(Protocol):
    def get_current_policy_version(self, policy_id: str) -> PolicyVersion: ...


class AuditStore(Protocol):
    def append(self, record: AuditRecord) -> None: ...


class NotificationStore(Protocol):
    def record_attempt(self, notification: Notification) -> None: ...
