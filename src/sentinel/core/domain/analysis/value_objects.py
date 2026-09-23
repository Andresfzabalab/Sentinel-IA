"""Value Objects owned by or attached to the Analysis Aggregate.

Per docs/02_Domain/Entities_Value_Objects.md: none of these has identity;
equality is by value; every instance is immutable once constructed. A
re-assessment produces a new value, never a mutation of an old one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ArtifactType = Literal[
    "source",
    "dockerfile",
    "k8s-helm",
    "terraform",
    "github-actions",
    "dependency-manifest",
    "other",
]
ChangeKind = Literal["added", "modified", "deleted"]
RiskLevel = Literal["low", "medium", "high", "critical"]
VerdictValue = Literal["PASS", "BLOCK"]

# Ordering used by Risk Assessment and Policy Evaluation to compare levels
# (Domain_Services.md's heuristics, Ubiquitous_Language.md's Severity/Risk
# distinction) -- purely a domain convention, not a database concept.
RISK_LEVEL_RANK: dict[str, int] = {"low": 0, "medium": 1, "high": 2, "critical": 3}


@dataclass(frozen=True)
class Artifact:
    """A single changed file, classified by type (Ubiquitous_Language.md)."""

    path: str
    type: ArtifactType
    change_kind: ChangeKind


@dataclass(frozen=True)
class PullRequestSnapshot:
    """A read-only, immutable snapshot of a GitHub PR at the moment an
    Analysis started (External Reference, per Domain_Concept_Model.md) --
    never present under a Mode B ad hoc manual trigger.

    `head_commit_sha` is not in Entities_Value_Objects.md's literal field
    list for this VO, but is included here as a practical necessity: it is
    the value Mode A's correlationId is deterministically derived from
    (Domain_Events.md) and is persisted as `analysis.pr_head_commit_sha`
    (Data_Model.md) -- the snapshot would otherwise have no way to carry it.
    """

    provider: str
    pr_number: int
    base_branch: str
    head_branch: str
    author: str
    head_commit_sha: str
    changed_file_paths: tuple[str, ...]


@dataclass(frozen=True)
class Severity:
    """The intrinsic rating a scanner assigns at normalization time --
    tool-assigned and context-free. Set once, never edited (Ubiquitous_Language.md).
    """

    level: RiskLevel
    raw_value: str | None = None


@dataclass(frozen=True)
class Risk:
    """SentinelAI's own, context-adjusted assessment of a Finding, produced
    exclusively by the Risk Engine (P-03) -- deterministic function of a
    Severity plus the heuristic factors applied.
    """

    adjusted_level: RiskLevel
    heuristics_applied: tuple[str, ...] = ()


@dataclass(frozen=True)
class SecurityScore:
    """A single deterministic aggregate measure over all risk-assessed
    Findings in one Analysis (Ubiquitous_Language.md). Not the verdict --
    only an input to Policy Evaluation.
    """

    value: float
    computed_from: tuple[str, ...] = ()  # finding ids that contributed


@dataclass(frozen=True)
class Verdict:
    """PASS | BLOCK, plus exactly which PolicyVersion and rule(s) produced
    it. Only ever constructed by Policy Evaluation (P-02, P-04) -- this
    type carries no other producer anywhere in the domain.
    """

    value: VerdictValue
    policy_version_id: str
    triggered_rules: tuple[str, ...] = ()
