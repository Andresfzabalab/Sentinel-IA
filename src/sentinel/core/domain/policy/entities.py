"""Policy Aggregate Root.

Publishing a new version never edits a prior version's content -- every
historical version stays byte-identical and retrievable, because a past
verdict must be reconstructable against the exact version that produced it
(QA-01).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sentinel.core.domain.exceptions import DuplicatePolicyVersion
from sentinel.core.domain.policy.value_objects import PolicyVersion


@dataclass
class Policy:
    id: str
    created_at: str
    versions: list[PolicyVersion] = field(default_factory=list)
    current_version_id: str | None = None

    def publish_version(self, version: PolicyVersion) -> None:
        """T-Policy -- Version Published. Rejects a version_number already
        used for this policy, rather than silently overwriting it
        (Persistence_Strategy.md's UNIQUE(policy_id, version_number) is the
        storage-level mirror of this same rule).
        """
        if version.policy_id != self.id:
            raise ValueError(f"version.policy_id {version.policy_id!r} does not match policy {self.id!r}")

        if any(v.version_number == version.version_number for v in self.versions):
            raise DuplicatePolicyVersion(
                f"policy {self.id!r} already has version_number {version.version_number!r}"
            )

        self.versions.append(version)
        self.current_version_id = version.id

    def get_version(self, version_id: str) -> PolicyVersion | None:
        for version in self.versions:
            if version.id == version_id:
                return version
        return None

    @property
    def current_version(self) -> PolicyVersion | None:
        if self.current_version_id is None:
            return None
        return self.get_version(self.current_version_id)
