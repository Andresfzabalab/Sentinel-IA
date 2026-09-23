"""Proves Security Score Calculation is pure aggregation, deterministic."""

from __future__ import annotations

from sentinel.core.domain.services.security_score import ScoredFinding, calculate_security_score


def test_no_findings_yields_perfect_score() -> None:
    score = calculate_security_score(())

    assert score.value == 100.0
    assert score.computed_from == ()


def test_penalizes_by_risk_level() -> None:
    score = calculate_security_score((ScoredFinding(finding_id="f-1", risk_level="critical"),))

    assert score.value == 60.0
    assert score.computed_from == ("f-1",)


def test_score_floors_at_zero_never_negative() -> None:
    findings = tuple(ScoredFinding(finding_id=f"f-{i}", risk_level="critical") for i in range(10))

    score = calculate_security_score(findings)

    assert score.value == 0.0


def test_deterministic_recomputation_yields_the_same_value() -> None:
    findings = (
        ScoredFinding(finding_id="f-1", risk_level="high"),
        ScoredFinding(finding_id="f-2", risk_level="low"),
    )

    first = calculate_security_score(findings)
    second = calculate_security_score(findings)

    assert first == second
