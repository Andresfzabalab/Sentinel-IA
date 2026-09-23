"""RiskPort -- Internal Domain port wrapping the deterministic Risk
Assessment Service (docs/02_Domain/Ports_and_Interfaces.md). No I/O,
kept as an interface purely so it can be substituted with a fixture in
tests (QA-05).
"""

from __future__ import annotations

from typing import Protocol

from sentinel.core.domain.analysis.value_objects import Risk
from sentinel.core.domain.services.risk_assessment import RiskAssessmentInput, assess_risk_batch


class RiskPort(Protocol):
    def assess(self, inputs: tuple[RiskAssessmentInput, ...]) -> dict[str, Risk]: ...


class DomainRiskPort:
    """The one real implementation for the MVP: a direct, zero-I/O call
    into the pure Domain Service (P-03) -- never AIProviderPort.
    """

    def assess(self, inputs: tuple[RiskAssessmentInput, ...]) -> dict[str, Risk]:
        return assess_risk_batch(inputs)
