"""Fixtures that seed the minimum Sentinel Core config (policy + policy_version
+ repository) an Analysis row's foreign keys require.
"""

from __future__ import annotations

import pytest

from sentinel.infrastructure.core.sqlite.policy_store import (
    PolicyCreate,
    PolicyVersionPublish,
    SqlitePolicyStore,
)
from sentinel.infrastructure.core.sqlite.repository_config_store import (
    RepositoryCreate,
    SqliteRepositoryConfigStore,
)


@pytest.fixture()
def seeded_policy_version_id(sqlite_conn) -> str:
    store = SqlitePolicyStore(sqlite_conn)
    store.create_policy(PolicyCreate(id="policy-1", created_at="2026-01-01T00:00:00Z"))
    store.publish_version(
        PolicyVersionPublish(
            id="policy-1-v1",
            policy_id="policy-1",
            version_number=1,
            rules='{"blockOn": "critical"}',
            published_at="2026-01-01T00:00:00Z",
            published_by="devsecops-1",
        )
    )
    return "policy-1-v1"


@pytest.fixture()
def seeded_repository_id(sqlite_conn, seeded_policy_version_id) -> str:
    store = SqliteRepositoryConfigStore(sqlite_conn)
    store.create_repository(
        RepositoryCreate(
            id="repo-1",
            external_identifier="acme/widgets",
            enabled_scanners='["semgrep", "gitleaks"]',
            assigned_policy_id="policy-1",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
    )
    return "repo-1"
