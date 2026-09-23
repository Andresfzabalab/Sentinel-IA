"""Proves Risk Assessment is deterministic (P-03, QA-02) and applies its
heuristics as documented in Domain_Services.md.
"""

from __future__ import annotations

from sentinel.core.domain.analysis.value_objects import Severity
from sentinel.core.domain.services.risk_assessment import RiskAssessmentInput, assess_risk


def test_no_heuristics_applied_leaves_severity_unchanged() -> None:
    risk = assess_risk(RiskAssessmentInput(finding_id="f-1", severity=Severity(level="high"), artifact_path="app.py"))

    assert risk.adjusted_level == "high"
    assert risk.heuristics_applied == ()


def test_test_file_path_downgrades_one_level() -> None:
    risk = assess_risk(RiskAssessmentInput(finding_id="f-1", severity=Severity(level="high"), artifact_path="tests/test_app.py"))

    assert risk.adjusted_level == "medium"
    assert "path_pattern:test_file_downgrade" in risk.heuristics_applied


def test_downgrade_floors_at_low_never_goes_negative() -> None:
    risk = assess_risk(RiskAssessmentInput(finding_id="f-1", severity=Severity(level="low"), artifact_path="tests/test_app.py"))

    assert risk.adjusted_level == "low"


def test_correlation_density_upgrades_one_level() -> None:
    risk = assess_risk(
        RiskAssessmentInput(finding_id="f-1", severity=Severity(level="medium"), artifact_path="app.py", correlation_group_size=2)
    )

    assert risk.adjusted_level == "high"
    assert "correlation_density:multi_scanner_upgrade" in risk.heuristics_applied


def test_upgrade_caps_at_critical_never_exceeds() -> None:
    risk = assess_risk(
        RiskAssessmentInput(finding_id="f-1", severity=Severity(level="critical"), artifact_path="app.py", correlation_group_size=3)
    )

    assert risk.adjusted_level == "critical"


def test_both_heuristics_can_apply_together() -> None:
    risk = assess_risk(
        RiskAssessmentInput(
            finding_id="f-1", severity=Severity(level="high"), artifact_path="tests/test_app.py", correlation_group_size=2
        )
    )

    # -1 (test file) then +1 (correlation) nets back to 'high'.
    assert risk.adjusted_level == "high"
    assert set(risk.heuristics_applied) == {"path_pattern:test_file_downgrade", "correlation_density:multi_scanner_upgrade"}


def test_deterministic_same_input_always_produces_the_same_output() -> None:
    """QA-02: run twice, byte-identical result."""
    finding_input = RiskAssessmentInput(finding_id="f-1", severity=Severity(level="high"), artifact_path="app.py", correlation_group_size=2)

    first = assess_risk(finding_input)
    second = assess_risk(finding_input)

    assert first == second
