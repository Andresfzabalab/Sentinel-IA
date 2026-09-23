"""Risk Assessment Service -- DETERMINISTIC (P-03).

Per docs/02_Domain/Domain_Services.md: reads Analysis's Findings plus
configured heuristics, outputs a Risk value per Finding. Never calls
AIProviderPort. Given identical inputs and identical configuration, always
produces the same output (QA-02).
"""

from __future__ import annotations

from dataclasses import dataclass

from sentinel.core.domain.analysis.value_objects import RISK_LEVEL_RANK, Risk, RiskLevel, Severity

_LEVELS_BY_RANK: dict[int, RiskLevel] = {rank: level for level, rank in RISK_LEVEL_RANK.items()}
_MAX_RANK = max(_LEVELS_BY_RANK)
_MIN_RANK = min(_LEVELS_BY_RANK)


def _shift_level(level: RiskLevel, delta: int) -> RiskLevel:
    rank = RISK_LEVEL_RANK[level] + delta
    rank = max(_MIN_RANK, min(_MAX_RANK, rank))
    return _LEVELS_BY_RANK[rank]


@dataclass(frozen=True)
class RiskAssessmentInput:
    """One Finding's inputs to Risk Assessment -- deliberately not the
    Finding entity itself, so this service stays a pure function with no
    dependency on the Aggregate's mutable state.
    """

    finding_id: str
    severity: Severity
    artifact_path: str
    correlation_group_size: int = 1  # how many NormalizedFindings share this Finding's correlation group


def assess_risk(finding_input: RiskAssessmentInput) -> Risk:
    """Heuristics applied, in order:

    1. Path pattern: a finding in a path containing 'test' is downgraded
       one level (floored at 'low') -- test code is lower real-world risk.
    2. Correlation density: a finding independently confirmed by two or
       more signals (correlation_group_size >= 2) is upgraded one level
       (capped at 'critical') -- multiple tools agreeing raises confidence.

    Both heuristics may apply to the same Finding; they are evaluated in
    this fixed order so the result is reproducible byte-for-byte given the
    same input (QA-02).
    """
    level = finding_input.severity.level
    applied: list[str] = []

    if "test" in finding_input.artifact_path.lower():
        level = _shift_level(level, -1)
        applied.append("path_pattern:test_file_downgrade")

    if finding_input.correlation_group_size >= 2:
        level = _shift_level(level, +1)
        applied.append("correlation_density:multi_scanner_upgrade")

    return Risk(adjusted_level=level, heuristics_applied=tuple(applied))


def assess_risk_batch(inputs: tuple[RiskAssessmentInput, ...]) -> dict[str, Risk]:
    return {i.finding_id: assess_risk(i) for i in inputs}
