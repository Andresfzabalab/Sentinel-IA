"""Repository Aggregate Root.

Per docs/02_Domain/Entities_Value_Objects.md: a Repository must have at
least a default Policy assignment before any Analysis can produce a
verdict -- an Analysis must never fall back to "no policy" silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sentinel.core.domain.exceptions import RepositoryMissingPolicy


@dataclass
class Repository:
    id: str
    external_identifier: str
    assigned_policy_id: str
    created_at: str
    updated_at: str
    provider: str = "github"
    enabled_scanners: tuple[str, ...] = ()
    ai_provider_config: dict | None = None
    active: bool = True

    def __post_init__(self) -> None:
        if not self.assigned_policy_id:
            raise RepositoryMissingPolicy(f"repository {self.id!r} has no assigned_policy_id")

    def update_configuration(
        self,
        *,
        enabled_scanners: tuple[str, ...] | None = None,
        assigned_policy_id: str | None = None,
        ai_provider_config: dict | None = None,
        active: bool | None = None,
        updated_at: str,
    ) -> None:
        """T-Repo -- Configuration Changed. Never retroactively affects an
        Analysis already `running`, which already read its configuration
        at its own T1 (Application_Use_Cases.md UC-3).
        """
        if assigned_policy_id is not None and not assigned_policy_id:
            raise RepositoryMissingPolicy(f"repository {self.id!r} cannot be updated with an empty policy id")

        if enabled_scanners is not None:
            self.enabled_scanners = enabled_scanners
        if assigned_policy_id is not None:
            self.assigned_policy_id = assigned_policy_id
        if ai_provider_config is not None:
            self.ai_provider_config = ai_provider_config
        if active is not None:
            self.active = active
        self.updated_at = updated_at
