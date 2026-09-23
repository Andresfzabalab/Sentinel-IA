"""Security Score Calculation Service -- pure aggregation, no side effects,
no external calls (docs/02_Domain/Domain_Services.md).
"""

from __future__ import annotations

from dataclasses import dataclass

from sentinel.core.domain.analysis.value_objects import RiskLevel, SecurityScore

_STARTING_SCORE = 100.0
_PENALTY_BY_LEVEL: dict[RiskLevel, float] = {"low": 2.0, "medium": 10.0, "high": 20.0, "critical": 40.0}


@dataclass(frozen=True)
class ScoredFinding:
    finding_id: str
    risk_level: RiskLevel


def calculate_security_score(findings: tuple[ScoredFinding, ...]) -> SecurityScore:
    """Starts at 100 and subtracts a fixed penalty per Finding's Risk
    level, floored at 0. Recomputing with the same Findings always yields
    the same value (Entities_Value_Objects.md's Security Score VO).
    """
    score = _STARTING_SCORE
    for finding in findings:
        score -= _PENALTY_BY_LEVEL[finding.risk_level]
    score = max(0.0, score)

    return SecurityScore(value=score, computed_from=tuple(f.finding_id for f in findings))
