"""Proves Policy Evaluation: the sole producer of a Verdict, deterministic
(QA-02, P-04), and UC-9's suppression semantics.
"""

from __future__ import annotations

from sentinel.core.domain.analysis.value_objects import SecurityScore
from sentinel.core.domain.policy.value_objects import PolicyVersion
from sentinel.core.domain.services.policy_evaluation import PolicyFinding, evaluate_policy


def _policy_version(rules: dict) -> PolicyVersion:
    return PolicyVersion(id="pv-1", policy_id="p-1", version_number=1, rules=rules, published_at="t0", published_by="a")


def test_passes_when_no_rule_is_triggered() -> None:
    findings = (PolicyFinding(finding_id="f-1", risk_level="low", rule_or_check_id="r1", artifact_path="app.py"),)
    result = evaluate_policy(findings, SecurityScore(value=95.0), _policy_version({"blockOnSeverity": "critical"}))

    assert result.verdict.value == "PASS"
    assert result.verdict.triggered_rules == ()


def test_blocks_when_severity_threshold_is_met_or_exceeded() -> None:
    findings = (PolicyFinding(finding_id="f-1", risk_level="critical", rule_or_check_id="r1", artifact_path="app.py"),)
    result = evaluate_policy(findings, SecurityScore(value=60.0), _policy_version({"blockOnSeverity": "critical"}))

    assert result.verdict.value == "BLOCK"
    assert len(result.verdict.triggered_rules) == 1


def test_blocks_when_score_is_below_threshold_even_with_low_severity_findings() -> None:
    findings = (PolicyFinding(finding_id="f-1", risk_level="low", rule_or_check_id="r1", artifact_path="app.py"),)
    result = evaluate_policy(findings, SecurityScore(value=10.0), _policy_version({"blockIfScoreBelow": 50}))

    assert result.verdict.value == "BLOCK"


def test_verdict_always_carries_the_exact_policy_version_id() -> None:
    result = evaluate_policy((), SecurityScore(value=100.0), _policy_version({}))

    assert result.verdict.policy_version_id == "pv-1"


def test_suppressed_findings_are_excluded_from_the_block_decision_but_still_identified() -> None:
    findings = (
        PolicyFinding(finding_id="f-1", risk_level="critical", rule_or_check_id="known-false-positive", artifact_path="app.py"),
    )
    policy_version = _policy_version(
        {
            "blockOnSeverity": "critical",
            "suppressions": [{"ruleOrCheckId": "known-false-positive", "artifactPath": "app.py"}],
        }
    )

    result = evaluate_policy(findings, SecurityScore(value=60.0), policy_version)

    assert result.verdict.value == "PASS"
    assert result.suppressed_finding_ids == ("f-1",)


def test_suppression_is_scoped_to_the_matching_artifact_path_prefix_only() -> None:
    findings = (
        PolicyFinding(finding_id="f-1", risk_level="critical", rule_or_check_id="rule-x", artifact_path="tests/fixture.py"),
        PolicyFinding(finding_id="f-2", risk_level="critical", rule_or_check_id="rule-x", artifact_path="app/prod.py"),
    )
    policy_version = _policy_version(
        {"blockOnSeverity": "critical", "suppressions": [{"ruleOrCheckId": "rule-x", "artifactPath": "tests/"}]}
    )

    result = evaluate_policy(findings, SecurityScore(value=60.0), policy_version)

    assert result.suppressed_finding_ids == ("f-1",)
    assert result.verdict.value == "BLOCK"  # f-2 still triggers the block


def test_deterministic_same_inputs_always_produce_the_same_verdict() -> None:
    findings = (PolicyFinding(finding_id="f-1", risk_level="high", rule_or_check_id="r1", artifact_path="app.py"),)
    score = SecurityScore(value=70.0)
    policy_version = _policy_version({"blockOnSeverity": "high"})

    first = evaluate_policy(findings, score, policy_version)
    second = evaluate_policy(findings, score, policy_version)

    assert first == second


def test_verdict_is_unaffected_by_any_ai_related_context() -> None:
    """P-02/P-04: this service's signature has no AI-related parameter at
    all -- there is no code path through which AI could reach the verdict."""
    import inspect

    from sentinel.core.domain.services.policy_evaluation import evaluate_policy as fn

    parameters = list(inspect.signature(fn).parameters)
    assert not any("ai" in p.lower() for p in parameters)
