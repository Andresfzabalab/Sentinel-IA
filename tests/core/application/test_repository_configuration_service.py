"""Proves RepositoryConfigurationService (UC-3, Phase 7): T-Repo as a
callable application-layer operation, with every change audited."""

from __future__ import annotations

import pytest

from sentinel.core.application.repository_configuration_service import (
    RepositoryConfigurationChange,
    RepositoryConfigurationService,
    RepositoryRegistration,
)
from sentinel.core.domain.exceptions import RepositoryMissingPolicy
from sentinel.infrastructure.core.sqlite.audit_store import SqliteAuditStore
from sentinel.infrastructure.core.sqlite.audit_store_adapter import SqliteAuditStoreAdapter
from sentinel.infrastructure.core.sqlite.policy_store import PolicyCreate, SqlitePolicyStore
from sentinel.infrastructure.core.sqlite.repository_config_store import SqliteRepositoryConfigStore
from sentinel.infrastructure.core.sqlite.repository_config_store_adapter import (
    SqliteRepositoryConfigStoreAdapter,
)


@pytest.fixture()
def service(sqlite_conn):
    SqlitePolicyStore(sqlite_conn).create_policy(PolicyCreate(id="policy-1", created_at="t0"))
    return RepositoryConfigurationService(
        SqliteRepositoryConfigStoreAdapter(SqliteRepositoryConfigStore(sqlite_conn)),
        SqliteAuditStoreAdapter(SqliteAuditStore(sqlite_conn)),
        clock=lambda: "2026-01-01T00:00:00Z",
    )


def test_register_creates_a_repository_and_an_audit_record(service, sqlite_conn):
    repo = service.register(
        RepositoryRegistration(id="repo-1", external_identifier="acme/widgets", assigned_policy_id="policy-1"),
        actor="devsecops-1",
    )

    assert repo.id == "repo-1"
    rows = sqlite_conn.execute("SELECT * FROM audit_record WHERE event_type = 'RepositoryRegistered'").fetchall()
    assert len(rows) == 1
    assert rows[0]["actor"] == "devsecops-1"


def test_register_without_a_policy_is_rejected(service):
    with pytest.raises(RepositoryMissingPolicy):
        service.register(
            RepositoryRegistration(id="repo-1", external_identifier="acme/widgets", assigned_policy_id=""),
            actor="devsecops-1",
        )


def test_update_changes_only_the_submitted_fields_and_audits_before_after(service, sqlite_conn):
    service.register(
        RepositoryRegistration(
            id="repo-1", external_identifier="acme/widgets", assigned_policy_id="policy-1",
            enabled_scanners=("semgrep",),
        ),
        actor="devsecops-1",
    )

    updated = service.update(
        "repo-1", RepositoryConfigurationChange(enabled_scanners=("semgrep", "gitleaks")), actor="devsecops-2"
    )

    assert updated.enabled_scanners == ("semgrep", "gitleaks")
    assert updated.assigned_policy_id == "policy-1"  # unchanged

    rows = sqlite_conn.execute("SELECT * FROM audit_record WHERE event_type = 'RepositoryConfigurationChanged'").fetchall()
    assert len(rows) == 1
    assert rows[0]["actor"] == "devsecops-2"


def test_update_to_an_empty_policy_id_is_rejected_never_leaves_a_repository_without_one(service):
    service.register(
        RepositoryRegistration(id="repo-1", external_identifier="acme/widgets", assigned_policy_id="policy-1"),
        actor="devsecops-1",
    )

    with pytest.raises(RepositoryMissingPolicy):
        service.update("repo-1", RepositoryConfigurationChange(assigned_policy_id=""), actor="devsecops-1")
