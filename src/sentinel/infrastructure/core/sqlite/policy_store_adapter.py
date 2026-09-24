"""SqlitePolicyStoreAdapter -- implements the domain-facing `PolicyStore`
port on top of the row-level SqlitePolicyStore. Reconstructs a domain
PolicyVersion object so the Orchestrator never sees a sqlite3.Row
(P-01/P-06).
"""

from __future__ import annotations

import json

from sentinel.core.domain.exceptions import RepositoryMissingPolicy
from sentinel.core.domain.policy.value_objects import PolicyVersion
from sentinel.infrastructure.core.sqlite.policy_store import SqlitePolicyStore


class SqlitePolicyStoreAdapter:
    def __init__(self, store: SqlitePolicyStore) -> None:
        self._store = store

    def get_current_policy_version(self, policy_id: str) -> PolicyVersion:
        row = self._store.get_current_version(policy_id)
        if row is None:
            raise RepositoryMissingPolicy(f"policy {policy_id!r} has no published version")
        return self._to_domain(row)

    def get_version(self, policy_version_id: str) -> PolicyVersion:
        """Resolves a *specific* version by id -- used by Crash & Restart
        Recovery, which must re-evaluate an Analysis against the exact
        PolicyVersion it originally referenced, never "whatever is current
        now" (QA-01, QA-02).
        """
        row = self._store.get_policy_version(policy_version_id)
        if row is None:
            raise RepositoryMissingPolicy(f"policy_version {policy_version_id!r} not found")
        return self._to_domain(row)

    @staticmethod
    def _to_domain(row) -> PolicyVersion:
        return PolicyVersion(
            id=row["id"],
            policy_id=row["policy_id"],
            version_number=row["version_number"],
            rules=json.loads(row["rules"]),
            published_at=row["published_at"],
            published_by=row["published_by"],
        )
