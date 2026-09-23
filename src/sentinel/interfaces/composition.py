"""Composition root: the process entry point.

Enforces docs/03_API/Configuration_and_Secrets.md's Local Execution Gate --
a missing mandatory secret must stop the process before it ever starts
serving, with a clear, actionable error, never a partially-usable process.

This is the ONLY module allowed to import from every layer (domain,
ports, application, infrastructure) and wire them together --
Project_Structure.md's import direction rule exists specifically so this
file is the one place dependency injection happens.
"""

from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass

import uvicorn

from sentinel.core.application.analysis_orchestrator import AnalysisOrchestrator
from sentinel.core.ports.event_bus_port import InMemoryEventBus
from sentinel.core.ports.policy_port import DomainPolicyPort
from sentinel.core.ports.risk_port import DomainRiskPort
from sentinel.infrastructure.core.github.client import GitHubClient
from sentinel.infrastructure.core.github.repository_port_adapter import GitHubRepositoryPort
from sentinel.infrastructure.core.scanners.not_implemented_scanner_port import NotYetImplementedScannerPort
from sentinel.infrastructure.core.sqlite.analysis_store import SqliteAnalysisStore
from sentinel.infrastructure.core.sqlite.analysis_store_adapter import SqliteAnalysisStoreAdapter
from sentinel.infrastructure.core.sqlite.audit_store import SqliteAuditStore
from sentinel.infrastructure.core.sqlite.audit_store_adapter import SqliteAuditStoreAdapter
from sentinel.infrastructure.core.sqlite.connection import connect
from sentinel.infrastructure.core.sqlite.notification_store import SqliteNotificationStore
from sentinel.infrastructure.core.sqlite.notification_store_adapter import SqliteNotificationStoreAdapter
from sentinel.infrastructure.core.sqlite.policy_store import SqlitePolicyStore
from sentinel.infrastructure.core.sqlite.policy_store_adapter import SqlitePolicyStoreAdapter
from sentinel.infrastructure.core.sqlite.repository_config_store import SqliteRepositoryConfigStore
from sentinel.infrastructure.core.sqlite.repository_config_store_adapter import (
    SqliteRepositoryConfigStoreAdapter,
)
from sentinel.interfaces.http.app import create_app
from sentinel.shared.config import ConfigurationError, Settings, load_settings


@dataclass
class AppDependencies:
    """Everything the HTTP layer (webhook router, future DevSecOps API)
    needs, bundled once at startup. Deliberately exposes both the raw,
    row-level Sqlite*Store instances (needed for lookups the Orchestrator
    itself doesn't do, like resolving a Repository by its GitHub
    `owner/repo` identifier) and the fully wired Orchestrator.
    """

    settings: Settings
    connection: sqlite3.Connection
    repository_config_store: SqliteRepositoryConfigStore
    analysis_store: SqliteAnalysisStore
    orchestrator: AnalysisOrchestrator
    github_client: GitHubClient


def build_dependencies(settings: Settings, *, github_transport: object | None = None) -> AppDependencies:
    """`github_transport` is a narrow, deliberate escape hatch for tests: it
    lets a test supply an `httpx.MockTransport` so the webhook can be
    exercised end-to-end without real network calls, while every other
    line of this function is exactly the real production wiring.
    """
    connection = connect(settings.database_path)

    repository_config_store = SqliteRepositoryConfigStore(connection)
    policy_store = SqlitePolicyStore(connection)
    analysis_store = SqliteAnalysisStore(connection)
    audit_store = SqliteAuditStore(connection)
    notification_store = SqliteNotificationStore(connection)

    github_client = GitHubClient(settings.github_token, transport=github_transport)
    repository_port = GitHubRepositoryPort(github_client)
    scanner_port = NotYetImplementedScannerPort()  # replaced by real adapters in Phase 5

    orchestrator = AnalysisOrchestrator(
        repository_port=repository_port,
        scanner_port=scanner_port,
        risk_port=DomainRiskPort(),
        policy_port=DomainPolicyPort(),
        event_bus=InMemoryEventBus(),
        analysis_store=SqliteAnalysisStoreAdapter(analysis_store),
        repository_config_store=SqliteRepositoryConfigStoreAdapter(repository_config_store),
        policy_store=SqlitePolicyStoreAdapter(policy_store),
        audit_store=SqliteAuditStoreAdapter(audit_store),
        notification_store=SqliteNotificationStoreAdapter(notification_store),
    )

    return AppDependencies(
        settings=settings,
        connection=connection,
        repository_config_store=repository_config_store,
        analysis_store=analysis_store,
        orchestrator=orchestrator,
        github_client=github_client,
    )


def main() -> None:
    try:
        settings = load_settings()
    except ConfigurationError as exc:
        print(f"SentinelAI failed to start: {exc}", file=sys.stderr)
        sys.exit(1)

    dependencies = build_dependencies(settings)
    app = create_app(settings=settings, dependencies=dependencies)
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
