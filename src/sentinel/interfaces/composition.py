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
from sentinel.core.application.policy_publishing_service import PolicyPublishingService
from sentinel.core.application.repository_configuration_service import RepositoryConfigurationService
from sentinel.core.ports.event_bus_port import InMemoryEventBus
from sentinel.core.ports.policy_port import DomainPolicyPort
from sentinel.core.ports.risk_port import DomainRiskPort
from sentinel.infrastructure.core.github.client import GitHubClient
from sentinel.infrastructure.core.github.oauth_client import GitHubOAuthClient
from sentinel.infrastructure.core.github.repository_port_adapter import GitHubRepositoryPort
from sentinel.infrastructure.core.scanners.composite_scanner_port import CompositeScannerPort
from sentinel.infrastructure.core.scanners.git_checkout_provider import GitCheckoutProvider
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
from sentinel.infrastructure.core.sqlite.session_store import SqliteSessionStore
from sentinel.interfaces.http.app import create_app
from sentinel.shared.config import ConfigurationError, Settings, load_settings


@dataclass
class AppDependencies:
    """Everything the HTTP layer (webhook router, DevSecOps API) needs,
    bundled once at startup. Deliberately exposes both the raw, row-level
    Sqlite*Store instances (needed for lookups the Orchestrator itself
    doesn't do, like resolving a Repository by its GitHub `owner/repo`
    identifier) and the domain-facing adapters / application services the
    API routes call directly.
    """

    settings: Settings
    connection: sqlite3.Connection
    repository_config_store: SqliteRepositoryConfigStore
    analysis_store: SqliteAnalysisStore
    analysis_store_adapter: SqliteAnalysisStoreAdapter
    audit_store: SqliteAuditStore
    session_store: SqliteSessionStore
    orchestrator: AnalysisOrchestrator
    github_client: GitHubClient
    oauth_client: GitHubOAuthClient
    repository_configuration_service: RepositoryConfigurationService
    policy_publishing_service: PolicyPublishingService


def build_dependencies(
    settings: Settings,
    *,
    github_transport: object | None = None,
    oauth_transport: object | None = None,
    working_directory_port: object | None = None,
) -> AppDependencies:
    """`github_transport`, `oauth_transport`, and `working_directory_port`
    are narrow, deliberate escape hatches for tests: the first two let a
    test supply an `httpx.MockTransport` so the webhook and the OAuth flow
    can be exercised end-to-end without real network calls; the last lets
    a test skip the real `git clone` (which would otherwise dial out to
    github.com and could hang up to its timeout on a network-isolated CI
    runner) with a stub. Every other line of this function is exactly the
    real production wiring.
    """
    connection = connect(settings.database_path)

    repository_config_store = SqliteRepositoryConfigStore(connection)
    policy_store = SqlitePolicyStore(connection)
    analysis_store = SqliteAnalysisStore(connection)
    audit_store = SqliteAuditStore(connection)
    notification_store = SqliteNotificationStore(connection)
    session_store = SqliteSessionStore(connection)

    audit_store_adapter = SqliteAuditStoreAdapter(audit_store)

    github_client = GitHubClient(settings.github_token, transport=github_transport)
    oauth_client = GitHubOAuthClient(
        settings.github_oauth_client_id, settings.github_oauth_client_secret, transport=oauth_transport
    )
    repository_port = GitHubRepositoryPort(github_client)
    scanner_port = CompositeScannerPort()  # Semgrep/Bandit/Trivy/Gitleaks/Checkov (Phase 5)
    working_directory_port = working_directory_port or GitCheckoutProvider(settings.github_token)  # real PR checkout (Phase 6)

    orchestrator = AnalysisOrchestrator(
        repository_port=repository_port,
        scanner_port=scanner_port,
        risk_port=DomainRiskPort(),
        policy_port=DomainPolicyPort(),
        event_bus=InMemoryEventBus(),
        analysis_store=SqliteAnalysisStoreAdapter(analysis_store),
        repository_config_store=SqliteRepositoryConfigStoreAdapter(repository_config_store),
        policy_store=SqlitePolicyStoreAdapter(policy_store),
        audit_store=audit_store_adapter,
        notification_store=SqliteNotificationStoreAdapter(notification_store),
        working_directory_port=working_directory_port,
    )

    repository_configuration_service = RepositoryConfigurationService(
        SqliteRepositoryConfigStoreAdapter(repository_config_store), audit_store_adapter
    )
    policy_publishing_service = PolicyPublishingService(SqlitePolicyStoreAdapter(policy_store), audit_store_adapter)

    return AppDependencies(
        settings=settings,
        connection=connection,
        repository_config_store=repository_config_store,
        analysis_store=analysis_store,
        analysis_store_adapter=SqliteAnalysisStoreAdapter(analysis_store),
        audit_store=audit_store,
        session_store=session_store,
        orchestrator=orchestrator,
        github_client=github_client,
        oauth_client=oauth_client,
        repository_configuration_service=repository_configuration_service,
        policy_publishing_service=policy_publishing_service,
    )


def main() -> None:
    try:
        settings = load_settings()
    except ConfigurationError as exc:
        print(f"SentinelAI failed to start: {exc}", file=sys.stderr)
        sys.exit(1)

    dependencies = build_dependencies(settings)

    # Crash & Restart Recovery (Persistence_Strategy.md) -- must run once,
    # before accepting any new webhook, so no row is ever left permanently
    # 'running' from a prior process's abrupt termination.
    dependencies.orchestrator.recover_incomplete_analyses()

    app = create_app(settings=settings, dependencies=dependencies)
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
