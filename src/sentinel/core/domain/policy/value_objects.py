"""PolicyVersion Value Object.

Immutable once published -- this is the object an Analysis actually
references, never "the current Policy" as a mutable thing
(Ubiquitous_Language.md). `rules` carries thresholds and, per UC-9,
suppression rules together -- suppression is content within a version,
never a separate mechanism.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PolicyVersion:
    id: str
    policy_id: str
    version_number: int
    rules: dict[str, Any]
    published_at: str
    published_by: str
