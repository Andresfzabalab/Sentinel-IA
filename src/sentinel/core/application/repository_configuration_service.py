"""Repository Configuration -- UC-3's callable application-layer operation
(Implementation_Strategy.md's Phase 7). Thin by design (Domain_Services.md):
it coordinates the RepositoryConfigStore port and Audit, encoding no
business rule itself -- the Repository entity's own constructor and
`update_configuration()` already enforce the "always has a Policy" invariant.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sentinel.core.domain.audit.entities import AuditRecord
from sentinel.core.domain.repository.entities import Repository
from sentinel.core.ports.store_ports import AuditStore, PolicyStore, RepositoryConfigStore


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class RepositoryRegistration:
    id: str
    external_identifier: str
    assigned_policy_id: str
    enabled_scanners: tuple[str, ...] = ()
    ai_provider_config: dict | None = None
    provider: str = "github"


@dataclass(frozen=True)
class RepositoryConfigurationChange:
    """Only the fields DevSecOps actually submitted are set; the rest are
    left unchanged (Repository.update_configuration()'s own semantics).
    """

    enabled_scanners: tuple[str, ...] | None = None
    assigned_policy_id: str | None = None
    ai_provider_config: dict | None = None
    active: bool | None = None


class RepositoryConfigurationService:
    def __init__(
        self,
        repository_config_store: RepositoryConfigStore,
        audit_store: AuditStore,
        policy_store: PolicyStore,
        *,
        clock: "callable[[], str]" = _utc_now_iso,
    ) -> None:
        self._repository_config_store = repository_config_store
        self._audit_store = audit_store
        self._policy_store = policy_store
        self._clock = clock

    def register(self, registration: RepositoryRegistration, *, actor: str) -> Repository:
        # Raises RepositoryMissingPolicy if the policy has no published
        # version -- a Repository must never be registered pointing at a
        # Policy that cannot actually be evaluated (Error_Handling_and_Resilience.md's
        # "Invalid configuration submitted" row).
        self._policy_store.get_current_policy_version(registration.assigned_policy_id)

        now = self._clock()
        repository = Repository(
            id=registration.id,
            external_identifier=registration.external_identifier,
            assigned_policy_id=registration.assigned_policy_id,
            created_at=now,
            updated_at=now,
            provider=registration.provider,
            enabled_scanners=registration.enabled_scanners,
            ai_provider_config=registration.ai_provider_config,
        )
        self._repository_config_store.create(repository)

        self._audit_store.append(
            AuditRecord(
                id=f"{registration.id}-audit-registered-{now}",
                actor=actor,
                event_type="RepositoryRegistered",
                origin="sentinel-core",
                payload={"repositoryId": registration.id, "externalIdentifier": registration.external_identifier},
                created_at=now,
            )
        )
        return repository

    def update(self, repository_id: str, change: RepositoryConfigurationChange, *, actor: str) -> Repository:
        """T-Repo -- Configuration Changed (UC-3). Never retroactively
        affects an Analysis already `running`, which already read its
        configuration at its own T1.
        """
        if change.assigned_policy_id is not None:
            # Same "must actually be evaluable" guard as register() -- an
            # update pointing at a nonexistent/unpublished Policy is
            # rejected here, at configuration time, never discovered later
            # when an Analysis tries to evaluate against it.
            self._policy_store.get_current_policy_version(change.assigned_policy_id)

        repository = self._repository_config_store.get_repository(repository_id)
        before = {
            "enabledScanners": list(repository.enabled_scanners),
            "assignedPolicyId": repository.assigned_policy_id,
            "active": repository.active,
        }

        now = self._clock()
        repository.update_configuration(
            enabled_scanners=change.enabled_scanners,
            assigned_policy_id=change.assigned_policy_id,
            ai_provider_config=change.ai_provider_config,
            active=change.active,
            updated_at=now,
        )
        self._repository_config_store.update(repository)

        self._audit_store.append(
            AuditRecord(
                id=f"{repository_id}-audit-config-{now}",
                actor=actor,
                event_type="RepositoryConfigurationChanged",
                origin="sentinel-core",
                payload={
                    "repositoryId": repository_id,
                    "before": before,
                    "after": {
                        "enabledScanners": list(repository.enabled_scanners),
                        "assignedPolicyId": repository.assigned_policy_id,
                        "active": repository.active,
                    },
                },
                created_at=now,
            )
        )
        return repository
