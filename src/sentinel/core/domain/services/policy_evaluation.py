"""Policy Evaluation Service -- DETERMINISTIC and the ONLY producer of a
Verdict (P-04). Never calls AIProviderPort. Must produce the same verdict
for the same (Findings, Risk, PolicyVersion) triple (QA-02).

Policy rules shape (PolicyVersion.rules, per docs/02_Domain/Application_Use_Cases.md
UC-9 and Aggregates_and_Boundaries.md's Policy section -- suppression is
just content within a version, not a separate mechanism):

    {
        "blockOnSeverity": "critical" | "high" | "medium" | "low" | null,
        "blockIfScoreBelow": <number> | null,
        "suppressions": [
            {"ruleOrCheckId": "<str>", "artifactPath": "<exact or prefix match>"}
        ]
    }
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sentinel.core.domain.analysis.value_objects import RISK_LEVEL_RANK, RiskLevel, SecurityScore, Verdict
from sentinel.core.domain.policy.value_objects import PolicyVersion


@dataclass(frozen=True)
class PolicyFinding:
    """One Finding's inputs to Policy Evaluation -- deliberately not the
    Finding entity itself, keeping this service a pure function.
    """

    finding_id: str
    risk_level: RiskLevel
    rule_or_check_id: str
    artifact_path: str


@dataclass(frozen=True)
class PolicyEvaluationResult:
    verdict: Verdict
    suppressed_finding_ids: tuple[str, ...]


def _is_suppressed(finding: PolicyFinding, suppressions: list[dict[str, Any]]) -> bool:
    for rule in suppressions:
        rule_matches = rule.get("ruleOrCheckId") == finding.rule_or_check_id
        path_pattern = rule.get("artifactPath")
        path_matches = path_pattern is None or finding.artifact_path.startswith(path_pattern)
        if rule_matches and path_matches:
            return True
    return False


def evaluate_policy(
    findings: tuple[PolicyFinding, ...],
    security_score: SecurityScore,
    policy_version: PolicyVersion,
) -> PolicyEvaluationResult:
    """Suppressed Findings are still computed and recorded exactly as any
    other Finding -- suppression affects only how this evaluation weighs
    them toward the verdict, never the Finding/Risk data itself (UC-9).
    """
    suppressions = policy_version.rules.get("suppressions", [])
    suppressed_ids = tuple(f.finding_id for f in findings if _is_suppressed(f, suppressions))
    suppressed_set = set(suppressed_ids)

    triggered_rules: list[str] = []

    severity_threshold = policy_version.rules.get("blockOnSeverity")
    if severity_threshold:
        threshold_rank = RISK_LEVEL_RANK[severity_threshold]
        for finding in findings:
            if finding.finding_id in suppressed_set:
                continue
            if RISK_LEVEL_RANK[finding.risk_level] >= threshold_rank:
                triggered_rules.append(
                    f"blockOnSeverity>={severity_threshold}:finding={finding.finding_id}"
                )

    score_threshold = policy_version.rules.get("blockIfScoreBelow")
    if score_threshold is not None and security_score.value < score_threshold:
        triggered_rules.append(f"blockIfScoreBelow={score_threshold}:score={security_score.value}")

    verdict_value = "BLOCK" if triggered_rules else "PASS"
    verdict = Verdict(
        value=verdict_value,
        policy_version_id=policy_version.id,
        triggered_rules=tuple(triggered_rules),
    )

    return PolicyEvaluationResult(verdict=verdict, suppressed_finding_ids=suppressed_ids)
