"""SqliteRepositoryConfigStoreAdapter -- implements the domain-facing
`RepositoryConfigStore` port on top of the row-level
SqliteRepositoryConfigStore. Reconstructs a domain Repository object so
the Orchestrator never sees a sqlite3.Row (P-01/P-06).
"""

from __future__ import annotations

import json

from sentinel.core.domain.repository.entities import Repository
from sentinel.infrastructure.core.sqlite.repository_config_store import (
    RepositoryConfigUpdate,
    RepositoryCreate,
    SqliteRepositoryConfigStore,
)


class SqliteRepositoryConfigStoreAdapter:
    def __init__(self, store: SqliteRepositoryConfigStore) -> None:
        self._store = store

    def get_repository(self, repository_id: str) -> Repository:
        row = self._store.get_repository(repository_id)
        if row is None:
            raise KeyError(f"repository {repository_id!r} not found")
        return self._to_domain(row)

    def create(self, repository: Repository) -> None:
        self._store.create_repository(
            RepositoryCreate(
                id=repository.id,
                external_identifier=repository.external_identifier,
                enabled_scanners=json.dumps(list(repository.enabled_scanners)),
                assigned_policy_id=repository.assigned_policy_id,
                created_at=repository.created_at,
                updated_at=repository.updated_at,
                provider=repository.provider,
                ai_provider_config=json.dumps(repository.ai_provider_config) if repository.ai_provider_config else None,
                active=repository.active,
            )
        )

    def update(self, repository: Repository) -> None:
        self._store.update_configuration(
            RepositoryConfigUpdate(
                id=repository.id,
                enabled_scanners=json.dumps(list(repository.enabled_scanners)),
                assigned_policy_id=repository.assigned_policy_id,
                active=repository.active,
                updated_at=repository.updated_at,
                ai_provider_config=json.dumps(repository.ai_provider_config) if repository.ai_provider_config else None,
            )
        )

    @staticmethod
    def _to_domain(row) -> Repository:
        return Repository(
            id=row["id"],
            external_identifier=row["external_identifier"],
            assigned_policy_id=row["assigned_policy_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            provider=row["provider"],
            enabled_scanners=tuple(json.loads(row["enabled_scanners"])),
            ai_provider_config=json.loads(row["ai_provider_config"]) if row["ai_provider_config"] else None,
            active=bool(row["active"]),
        )
