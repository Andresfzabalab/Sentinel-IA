"""SqlitePolicyStoreAdapter -- implements the domain-facing `PolicyStore`
port on top of the row-level SqlitePolicyStore. Reconstructs a domain
PolicyVersion object so the Orchestrator never sees a sqlite3.Row
(P-01/P-06).
"""

from __future__ import annotations

import json
import uuid

from sentinel.core.domain.exceptions import DuplicatePolicyVersion, RepositoryMissingPolicy
from sentinel.core.domain.policy.value_objects import PolicyVersion
from sentinel.infrastructure.core.sqlite.policy_store import (
    DuplicatePolicyVersion as SqliteDuplicatePolicyVersion,
)
from sentinel.infrastructure.core.sqlite.policy_store import (
    PolicyCreate,
    PolicyVersionPublish,
    SqlitePolicyStore,
)


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

    def create_policy(self, policy_id: str, created_at: str) -> None:
        self._store.create_policy(PolicyCreate(id=policy_id, created_at=created_at))

    def ensure_policy_exists(self, policy_id: str, created_at: str) -> None:
        if self._store.get_policy(policy_id) is None:
            self._store.create_policy(PolicyCreate(id=policy_id, created_at=created_at))

    def next_version_number(self, policy_id: str) -> int:
        current_max = self._store.get_max_version_number(policy_id)
        return 1 if current_max is None else current_max + 1

    def publish_version(
        self, policy_id: str, version_number: int, rules: dict, published_at: str, published_by: str
    ) -> PolicyVersion:
        version_id = str(uuid.uuid4())
        try:
            self._store.publish_version(
                PolicyVersionPublish(
                    id=version_id, policy_id=policy_id, version_number=version_number,
                    rules=json.dumps(rules), published_at=published_at, published_by=published_by,
                )
            )
        except SqliteDuplicatePolicyVersion as exc:
            # Translated to the domain-level exception (core/domain/exceptions.py)
            # so callers in core/application/ never need to import infrastructure/ (P-01/P-06).
            raise DuplicatePolicyVersion(str(exc)) from exc

        return PolicyVersion(
            id=version_id, policy_id=policy_id, version_number=version_number,
            rules=rules, published_at=published_at, published_by=published_by,
        )

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
