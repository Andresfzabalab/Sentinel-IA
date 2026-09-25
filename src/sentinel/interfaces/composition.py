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

from sentinel.ai_agent.agents.framework import AgentDefinition, AgentRegistry
from sentinel.ai_agent.agents.security_investigation_agent import AGENT_TYPE, SecurityInvestigationAgent
from sentinel.ai_agent.agents.tools import ALL_TOOL_NAMES, KnowledgeBaseTool
from sentinel.ai_agent.application.agent_execution_runner import AgentExecutionRunner
from sentinel.ai_agent.application.report_generation_service import ReportGenerationService
from sentinel.ai_agent.domain.entities import ExecutionLimits
from sentinel.core.application.analysis_orchestrator import AnalysisOrchestrator
from sentinel.core.application.policy_publishing_service import PolicyPublishingService
from sentinel.core.application.repository_configuration_service import RepositoryConfigurationService
from sentinel.core.ports.event_bus_port import InMemoryEventBus
from sentinel.core.ports.policy_port import DomainPolicyPort
from sentinel.core.ports.risk_port import DomainRiskPort
from sentinel.infrastructure.ai_agent.providers.null_provider import NullAIProvider
from sentinel.infrastructure.ai_agent.providers.ollama_provider import OllamaProvider
from sentinel.infrastructure.ai_agent.providers.openai_provider import OpenAIProvider
from sentinel.infrastructure.ai_agent.security_knowledge_base_adapter import (
    SecurityKnowledgeBaseCrossModuleAdapter,
)
from sentinel.infrastructure.ai_agent.security_result_query_adapter import SecurityResultQueryAdapter
from sentinel.infrastructure.ai_agent.sqlite.agent_execution_store import SqliteAgentExecutionStore
from sentinel.infrastructure.ai_agent.sqlite.agent_execution_store_adapter import (
    SqliteAgentExecutionStoreAdapter,
)
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
from sentinel.infrastructure.intelligence.sources.static_seed_source import StaticSeedSource
from sentinel.infrastructure.intelligence.sqlite.knowledge_base_store import SqliteKnowledgeBaseStore
from sentinel.infrastructure.intelligence.sqlite.knowledge_base_store_adapter import (
    SqliteKnowledgeBaseStoreAdapter,
    new_entry_id,
)
from sentinel.intelligence.application.knowledge_refresh_service import KnowledgeRefreshService
from sentinel.interfaces.http.app import create_app
from sentinel.shared.config import ConfigurationError, Settings, load_settings

# The finding categories SentinelAI's MVP scanners actually produce
# (Bounded_Contexts.md) -- what StaticSeedSource has curated guidance for.
_KNOWLEDGE_BASE_SEED_TOPICS: tuple[str, ...] = ("sast", "sca", "secret", "container", "iac")


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
    agent_execution_store: SqliteAgentExecutionStoreAdapter
    agent_execution_runner: AgentExecutionRunner
    report_generation_service: ReportGenerationService
    ai_agent_event_bus: InMemoryEventBus
    knowledge_base_store: SqliteKnowledgeBaseStoreAdapter


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

    # Sentinel Core's own EventBusPort instance. The AI & Agent Module never
    # shares it -- it gets a private instance below, connected only through
    # the one-directional AnalysisCompletedRelay (Module_Boundaries.md).
    core_event_bus = InMemoryEventBus()

    orchestrator = AnalysisOrchestrator(
        repository_port=repository_port,
        scanner_port=scanner_port,
        risk_port=DomainRiskPort(),
        policy_port=DomainPolicyPort(),
        event_bus=core_event_bus,
        analysis_store=SqliteAnalysisStoreAdapter(analysis_store),
        repository_config_store=SqliteRepositoryConfigStoreAdapter(repository_config_store),
        policy_store=SqlitePolicyStoreAdapter(policy_store),
        audit_store=audit_store_adapter,
        notification_store=SqliteNotificationStoreAdapter(notification_store),
        working_directory_port=working_directory_port,
    )

    repository_configuration_service = RepositoryConfigurationService(
        SqliteRepositoryConfigStoreAdapter(repository_config_store), audit_store_adapter, SqlitePolicyStoreAdapter(policy_store)
    )
    policy_publishing_service = PolicyPublishingService(SqlitePolicyStoreAdapter(policy_store), audit_store_adapter)

    # --- Security Intelligence & Data Module (Phase 9) -------------------
    # Seeding itself happens in main(), after schema migrations have run --
    # not here, since some callers (tests) build the schema only after
    # build_dependencies() returns.
    knowledge_base_store_adapter = SqliteKnowledgeBaseStoreAdapter(SqliteKnowledgeBaseStore(connection))

    # --- AI & Agent Module (Phase 9) --------------------------------------
    ai_provider = _select_ai_provider(settings)
    security_knowledge_base_port = SecurityKnowledgeBaseCrossModuleAdapter(knowledge_base_store_adapter)
    security_result_query_port = SecurityResultQueryAdapter(SqliteAnalysisStoreAdapter(analysis_store))
    agent_execution_store_adapter = SqliteAgentExecutionStoreAdapter(SqliteAgentExecutionStore(connection))

    agent_registry = AgentRegistry()
    agent_registry.register(
        AgentDefinition(
            agent_type=AGENT_TYPE,
            allowed_tools=ALL_TOOL_NAMES,
            execution_limits=ExecutionLimits(max_duration_seconds=60, max_tool_calls=50, max_output_size=4000),
        )
    )
    security_investigation_agent = SecurityInvestigationAgent(ai_provider, KnowledgeBaseTool(security_knowledge_base_port))

    agent_execution_runner = AgentExecutionRunner(
        agent_registry,
        security_investigation_agent,
        security_result_query_port,
        agent_execution_store_adapter,
        audit_store_adapter,
        agent_type=AGENT_TYPE,
    )

    # The AI & Agent Module's own, private EventBusPort instance -- never
    # shared with Sentinel Core's (Module_Boundaries.md).
    ai_agent_event_bus = InMemoryEventBus()
    ai_agent_event_bus.subscribe(
        "AnalysisCompleted",
        lambda payload: agent_execution_runner.run(payload["analysisId"], payload["correlationId"]),
    )
    # AnalysisCompletedRelay: the one-directional, single-event bridge from
    # Sentinel Core's bus to the AI & Agent Module's own bus
    # (Domain_Events.md) -- nothing here can call back upstream.
    core_event_bus.subscribe("AnalysisCompleted", lambda payload: ai_agent_event_bus.publish("AnalysisCompleted", payload))

    report_generation_service = ReportGenerationService(security_result_query_port, agent_execution_store_adapter)

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
        agent_execution_store=agent_execution_store_adapter,
        agent_execution_runner=agent_execution_runner,
        report_generation_service=report_generation_service,
        ai_agent_event_bus=ai_agent_event_bus,
        knowledge_base_store=knowledge_base_store_adapter,
    )


def seed_knowledge_base(dependencies: AppDependencies) -> tuple[str, ...]:
    """Publishes/refreshes the curated StaticSeedSource content into the
    Security Knowledge Base. Idempotent -- safe to call on every startup;
    skips any topic whose content hasn't changed since the last run.
    Must run only after schema migrations have created
    `security_knowledge_base_entry` (scripts/run_migrations.py) -- called
    from main(), never from build_dependencies() itself, since some callers
    (tests) create the schema only after build_dependencies() returns.
    """
    return KnowledgeRefreshService(StaticSeedSource(), dependencies.knowledge_base_store).refresh(
        _KNOWLEDGE_BASE_SEED_TOPICS, id_factory=new_entry_id
    )


def _select_ai_provider(settings: Settings) -> object:
    """QA-06 provider portability: chosen purely from which optional secret
    is configured, never a code change. Ollama (local) takes priority over
    OpenAI (API) when both happen to be set, since Technology_Strategy.md
    treats the local provider as the default/primary; NullAIProvider (always
    `AIProviderUnavailable`) is the graceful-degradation default when
    neither is configured (QA-04) -- the same failure path a real outage
    takes, not a distinct one.
    """
    ollama_base_url = settings.optional.get("OLLAMA_BASE_URL")
    if ollama_base_url:
        return OllamaProvider(ollama_base_url, "qwen2.5-coder")

    openai_api_key = settings.optional.get("OPENAI_API_KEY")
    if openai_api_key:
        return OpenAIProvider(openai_api_key)

    return NullAIProvider()


def main() -> None:
    try:
        settings = load_settings()
    except ConfigurationError as exc:
        print(f"SentinelAI failed to start: {exc}", file=sys.stderr)
        sys.exit(1)

    dependencies = build_dependencies(settings)
    seed_knowledge_base(dependencies)

    # Crash & Restart Recovery (Persistence_Strategy.md) -- must run once,
    # before accepting any new webhook, so no row is ever left permanently
    # 'running' from a prior process's abrupt termination.
    dependencies.orchestrator.recover_incomplete_analyses()

    app = create_app(settings=settings, dependencies=dependencies)
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
