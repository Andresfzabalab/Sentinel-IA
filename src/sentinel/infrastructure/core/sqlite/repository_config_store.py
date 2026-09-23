"""SqliteRepositoryConfigStore -- implements RepositoryConfigStore (T-Repo).

Touches only the `repository` table. A mid-flight configuration change
never retroactively affects an Analysis already `running` -- that Analysis
already read its configuration at its own T1 (Application_Use_Cases.md UC-3).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class RepositoryCreate:
    id: str
    external_identifier: str
    enabled_scanners: str  # JSON array
    assigned_policy_id: str
    created_at: str
    updated_at: str
    provider: str = "github"
    ai_provider_config: str | None = None  # JSON, references a provider name only -- never a secret
    active: bool = True


@dataclass(frozen=True)
class RepositoryConfigUpdate:
    id: str
    enabled_scanners: str
    assigned_policy_id: str
    active: bool
    updated_at: str
    ai_provider_config: str | None = None


class SqliteRepositoryConfigStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create_repository(self, repo: RepositoryCreate) -> None:
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE;")
        try:
            conn.execute(
                """
                INSERT INTO repository (
                    id, provider, external_identifier, enabled_scanners, assigned_policy_id,
                    ai_provider_config, active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    repo.id,
                    repo.provider,
                    repo.external_identifier,
                    repo.enabled_scanners,
                    repo.assigned_policy_id,
                    repo.ai_provider_config,
                    repo.active,
                    repo.created_at,
                    repo.updated_at,
                ),
            )
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    def update_configuration(self, update: RepositoryConfigUpdate) -> None:
        """T-Repo -- Configuration Changed."""
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE;")
        try:
            conn.execute(
                """
                UPDATE repository
                SET enabled_scanners = ?, assigned_policy_id = ?, ai_provider_config = ?,
                    active = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    update.enabled_scanners,
                    update.assigned_policy_id,
                    update.ai_provider_config,
                    update.active,
                    update.updated_at,
                    update.id,
                ),
            )
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    def get_repository(self, repository_id: str) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM repository WHERE id = ?", (repository_id,)).fetchone()

    def get_repository_by_external_identifier(self, external_identifier: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM repository WHERE external_identifier = ?", (external_identifier,)
        ).fetchone()
