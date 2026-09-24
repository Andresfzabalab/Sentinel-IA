"""Proves SqliteRepositoryConfigStoreAdapter's domain-facing create/update
(Phase 7's T-Repo callable operations)."""

from __future__ import annotations

import pytest

from sentinel.core.domain.exceptions import RepositoryMissingPolicy
from sentinel.core.domain.repository.entities import Repository
from sentinel.infrastructure.core.sqlite.policy_store import PolicyCreate, SqlitePolicyStore
from sentinel.infrastructure.core.sqlite.repository_config_store import SqliteRepositoryConfigStore
from sentinel.infrastructure.core.sqlite.repository_config_store_adapter import (
    SqliteRepositoryConfigStoreAdapter,
)


@pytest.fixture()
def seeded_policy_id(sqlite_conn) -> str:
    SqlitePolicyStore(sqlite_conn).create_policy(PolicyCreate(id="policy-1", created_at="t0"))
    return "policy-1"


def test_create_and_get_round_trip(sqlite_conn, seeded_policy_id):
    adapter = SqliteRepositoryConfigStoreAdapter(SqliteRepositoryConfigStore(sqlite_conn))

    repo = Repository(
        id="repo-1", external_identifier="acme/widgets", assigned_policy_id=seeded_policy_id,
        created_at="t0", updated_at="t0", enabled_scanners=("semgrep", "gitleaks"),
    )
    adapter.create(repo)

    loaded = adapter.get_repository("repo-1")
    assert loaded.external_identifier == "acme/widgets"
    assert loaded.enabled_scanners == ("semgrep", "gitleaks")
    assert loaded.assigned_policy_id == seeded_policy_id
    assert loaded.active is True


def test_update_persists_the_repositorys_current_full_state(sqlite_conn, seeded_policy_id):
    from sentinel.infrastructure.core.sqlite.repository_config_store import SqliteRepositoryConfigStore

    adapter = SqliteRepositoryConfigStoreAdapter(SqliteRepositoryConfigStore(sqlite_conn))
    repo = Repository(
        id="repo-1", external_identifier="acme/widgets", assigned_policy_id=seeded_policy_id,
        created_at="t0", updated_at="t0", enabled_scanners=("semgrep",),
    )
    adapter.create(repo)

    repo.update_configuration(enabled_scanners=("semgrep", "trivy"), active=False, updated_at="t1")
    adapter.update(repo)

    reloaded = adapter.get_repository("repo-1")
    assert reloaded.enabled_scanners == ("semgrep", "trivy")
    assert reloaded.active is False
    assert reloaded.updated_at == "t1"


def test_get_unknown_repository_raises_key_error(sqlite_conn):
    from sentinel.infrastructure.core.sqlite.repository_config_store import SqliteRepositoryConfigStore

    adapter = SqliteRepositoryConfigStoreAdapter(SqliteRepositoryConfigStore(sqlite_conn))

    with pytest.raises(KeyError):
        adapter.get_repository("does-not-exist")


def test_cannot_construct_a_repository_domain_object_without_a_policy():
    with pytest.raises(RepositoryMissingPolicy):
        Repository(id="r1", external_identifier="a/b", assigned_policy_id="", created_at="t0", updated_at="t0")
