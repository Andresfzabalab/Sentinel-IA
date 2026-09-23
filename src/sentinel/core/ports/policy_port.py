"""PolicyPort -- Internal Domain port wrapping the deterministic Policy
Evaluation Service (docs/02_Domain/Ports_and_Interfaces.md).

Computes a verdict *value* only -- it has no write capability. Applying
that value to the Analysis Aggregate (the write-once invariant) is
`Analysis.record_verdict()`, called by the Orchestrator, never by this port.
"""

from __future__ import annotations

from typing import Protocol

from sentinel.core.domain.analysis.value_objects import SecurityScore
from sentinel.core.domain.policy.value_objects import PolicyVersion
from sentinel.core.domain.services.policy_evaluation import (
    PolicyEvaluationResult,
    PolicyFinding,
    evaluate_policy,
)


class PolicyPort(Protocol):
    def evaluate(
        self, findings: tuple[PolicyFinding, ...], security_score: SecurityScore, policy_version: PolicyVersion
    ) -> PolicyEvaluationResult: ...


class DomainPolicyPort:
    """The one real implementation for the MVP: a direct, zero-I/O call
    into the pure Domain Service (P-04) -- never AIProviderPort.
    """

    def evaluate(
        self, findings: tuple[PolicyFinding, ...], security_score: SecurityScore, policy_version: PolicyVersion
    ) -> PolicyEvaluationResult:
        return evaluate_policy(findings, security_score, policy_version)
