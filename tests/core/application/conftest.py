"""Fixtures for Phase 3's application-layer tests: a real, temp-file
SQLite database (via the real Phase 1 *Store adapters, wrapped by their
domain-facing Phase 3 adapters) wired to the Analysis Orchestrator against
Fake RepositoryPort/ScannerPort (Testing_Strategy.md's Application-Layer
Tests). This conftest plays the role of a composition root for tests --
it is the one place allowed to import both `core/application/` and
`infrastructure/`, exactly like the real `interfaces/composition.py` will.
"""

from __future__ import annotations

import json

import pytest

from sentinel.core.application.analysis_orchestrator import AnalysisOrchestrator
from sentinel.core.ports.event_bus_port import InMemoryEventBus
from sentinel.core.ports.policy_port import DomainPolicyPort
from sentinel.core.ports.risk_port import DomainRiskPort
from sentinel.infrastructure.core.sqlite.analysis_store import SqliteAnalysisStore
from sentinel.infrastructure.core.sqlite.analysis_store_adapter import SqliteAnalysisStoreAdapter
from sentinel.infrastructure.core.sqlite.audit_store import SqliteAuditStore
from sentinel.infrastructure.core.sqlite.audit_store_adapter import SqliteAuditStoreAdapter
from sentinel.infrastructure.core.sqlite.connection import connect
from sentinel.infrastructure.core.sqlite.notification_store import SqliteNotificationStore
from sentinel.infrastructure.core.sqlite.notification_store_adapter import SqliteNotificationStoreAdapter
from sentinel.infrastructure.core.sqlite.policy_store import PolicyCreate, PolicyVersionPublish, SqlitePolicyStore
from sentinel.infrastructure.core.sqlite.policy_store_adapter import SqlitePolicyStoreAdapter
from sentinel.infrastructure.core.sqlite.repository_config_store import (
    RepositoryCreate,
    SqliteRepositoryConfigStore,
)
from sentinel.infrastructure.core.sqlite.repository_config_store_adapter import (
    SqliteRepositoryConfigStoreAdapter,
)
from sentinel.infrastructure.schema import create_full_schema
from tests.fakes.fake_repository_port import FakeRepositoryPort
from tests.fakes.fake_scanner_port import FakeScannerPort


@pytest.fixture()
def sqlite_conn(tmp_path):
    db_path = tmp_path / "orchestrator_test.sqlite"
    conn = connect(str(db_path))
    create_full_schema(conn)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture()
def analysis_store(sqlite_conn) -> SqliteAnalysisStore:
    return SqliteAnalysisStore(sqlite_conn)


@pytest.fixture()
def repository_config_store(sqlite_conn) -> SqliteRepositoryConfigStore:
    return SqliteRepositoryConfigStore(sqlite_conn)


@pytest.fixture()
def policy_store(sqlite_conn) -> SqlitePolicyStore:
    return SqlitePolicyStore(sqlite_conn)


@pytest.fixture()
def audit_store(sqlite_conn) -> SqliteAuditStore:
    return SqliteAuditStore(sqlite_conn)


@pytest.fixture()
def notification_store(sqlite_conn) -> SqliteNotificationStore:
    return SqliteNotificationStore(sqlite_conn)


def seed_policy_and_repository(
    policy_store: SqlitePolicyStore,
    repository_config_store: SqliteRepositoryConfigStore,
    *,
    repository_id: str = "repo-1",
    external_identifier: str = "acme/widgets",
    enabled_scanners: tuple[str, ...] = ("semgrep", "gitleaks"),
    policy_rules: dict | None = None,
) -> None:
    policy_store.create_policy(PolicyCreate(id="policy-1", created_at="t0"))
    policy_store.publish_version(
        PolicyVersionPublish(
            id="policy-1-v1",
            policy_id="policy-1",
            version_number=1,
            rules=json.dumps(policy_rules or {"blockOnSeverity": "critical"}),
            published_at="t0",
            published_by="devsecops-1",
        )
    )
    repository_config_store.create_repository(
        RepositoryCreate(
            id=repository_id,
            external_identifier=external_identifier,
            enabled_scanners=json.dumps(list(enabled_scanners)),
            assigned_policy_id="policy-1",
            created_at="t0",
            updated_at="t0",
        )
    )


@pytest.fixture()
def fake_repository_port() -> FakeRepositoryPort:
    return FakeRepositoryPort()


@pytest.fixture()
def fake_scanner_port() -> FakeScannerPort:
    return FakeScannerPort()


@pytest.fixture()
def build_orchestrator(
    analysis_store, repository_config_store, policy_store, audit_store, notification_store,
    fake_repository_port, fake_scanner_port,
):
    def _build(*, id_factory=None, clock=None, scanner_runtime_config=None) -> AnalysisOrchestrator:
        kwargs = dict(
            repository_port=fake_repository_port,
            scanner_port=fake_scanner_port,
            risk_port=DomainRiskPort(),
            policy_port=DomainPolicyPort(),
            event_bus=InMemoryEventBus(),
            analysis_store=SqliteAnalysisStoreAdapter(analysis_store),
            repository_config_store=SqliteRepositoryConfigStoreAdapter(repository_config_store),
            policy_store=SqlitePolicyStoreAdapter(policy_store),
            audit_store=SqliteAuditStoreAdapter(audit_store),
            notification_store=SqliteNotificationStoreAdapter(notification_store),
            scanner_runtime_config=scanner_runtime_config or {},
        )
        if id_factory is not None:
            kwargs["id_factory"] = id_factory
        if clock is not None:
            kwargs["clock"] = clock
        return AnalysisOrchestrator(**kwargs)

    return _build
