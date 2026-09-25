"""AIProviderPort -- Infrastructure port to the configured AI Provider
(Ollama or an API provider), per docs/02_Domain/Ports_and_Interfaces.md.

P-02, structurally: `AdvisoryResponse` has no field, at any nesting level,
capable of representing a verdict or a Security Score. This is not a
convention the adapter is trusted to follow -- the type itself cannot
carry one, so no code path downstream could read a verdict-shaped value
out of it even by mistake.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class AIProviderUnavailable(Exception):
    """Raised when the configured provider cannot be reached or times out.

    Caught by the Agent Execution Runner to produce `pending_unavailable`
    (AI_Agent_Architecture.md §8) -- never allowed to propagate, and never
    allowed to affect a verdict already fixed at T3 (P-02, QA-04).
    """


@dataclass(frozen=True)
class AdvisoryRequest:
    finding_category: str
    finding_rule_or_check_id: str
    finding_severity_level: str
    finding_risk_level: str | None
    artifact_path: str
    knowledge_base_content: str | None  # None means "no sufficient knowledge" (AI_Agent_Architecture.md §6)


@dataclass(frozen=True)
class AdvisoryResponse:
    explanation: str
    consequence_framing: str | None = None
    prioritization_hint: str | None = None
    remediation_suggestion: str | None = None
    # No `verdict` field. No `security_score` field. Never added (P-02).


class AIProviderPort(Protocol):
    def generate_advisory(self, request: AdvisoryRequest) -> AdvisoryResponse:
        """Raises AIProviderUnavailable on any failure/timeout -- never
        raises for a "no findings to explain" case (callers simply don't
        invoke this then); this is exclusively for provider-reachability
        failures.
        """
        ...
