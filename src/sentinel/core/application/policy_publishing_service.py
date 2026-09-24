"""Policy Publishing -- UC-4/UC-9's callable application-layer operation
(Implementation_Strategy.md's Phase 7). Suppression is just content inside
a new PolicyVersion's `rules` -- there is no separate "suppress a finding"
mechanism; publishing a suppression rule uses this exact same operation
(Aggregates_and_Boundaries.md's Policy section).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sentinel.core.domain.audit.entities import AuditRecord
from sentinel.core.domain.policy.value_objects import PolicyVersion
from sentinel.core.ports.store_ports import AuditStore, PolicyStore


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PolicyPublishingService:
    def __init__(
        self, policy_store: PolicyStore, audit_store: AuditStore, *, clock: "callable[[], str]" = _utc_now_iso
    ) -> None:
        self._policy_store = policy_store
        self._audit_store = audit_store
        self._clock = clock

    def create_policy(self, policy_id: str, *, actor: str) -> None:
        now = self._clock()
        self._policy_store.create_policy(policy_id, now)

        self._audit_store.append(
            AuditRecord(
                id=f"{policy_id}-audit-created-{now}",
                actor=actor,
                event_type="PolicyCreated",
                origin="sentinel-core",
                payload={"policyId": policy_id},
                created_at=now,
            )
        )

    def publish_version(self, policy_id: str, rules: dict, *, actor: str) -> PolicyVersion:
        """T-Policy -- Version Published. Never edits a prior version;
        existing Analyses referencing an older PolicyVersion are provably
        unaffected (QA-01) -- this method never touches the `analysis` table
        at all. Raises DuplicatePolicyVersion (core/domain/exceptions.py)
        if called twice for the same next version number in a race --
        callers should treat that as "retry with a fresh version number."
        """
        now = self._clock()
        version_number = self._policy_store.next_version_number(policy_id)

        version = self._policy_store.publish_version(
            policy_id, version_number, rules, published_at=now, published_by=actor
        )

        self._audit_store.append(
            AuditRecord(
                id=f"{policy_id}-audit-published-v{version_number}",
                actor=actor,
                event_type="PolicyVersionPublished",
                origin="sentinel-core",
                payload={
                    "policyId": policy_id,
                    "versionNumber": version_number,
                    "policyVersionId": version.id,
                    "rules": rules,
                },
                created_at=now,
            )
        )
        return version
