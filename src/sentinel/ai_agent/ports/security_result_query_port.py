"""SecurityResultQueryPort -- Cross-Module, read-only (docs/02_Domain/Ports_and_Interfaces.md).

Declared here, in the *consuming* module's ports/, per Project_Structure.md's
import direction: ai_agent/application/ may depend only on ai_agent/ports/,
never on core/ directly. Sentinel Core provides the concrete implementation
(infrastructure/ai_agent/security_result_query_adapter.py, wired at
composition time) -- this keeps the dependency direction exactly as
Module_Boundaries.md fixes it: "Sentinel Core depends on nothing else in
this diagram," so the interface a consumer needs is the consumer's own
contract, not an import of the producer's internals.

No write method exists on this port at all -- not "read-only by
convention," read-only because there is nothing else to call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

VerdictValue = Literal["PASS", "BLOCK"]


@dataclass(frozen=True)
class FindingView:
    finding_id: str
    scanner_id: str
    category: str
    artifact_path: str
    rule_or_check_id: str
    severity_level: str
    risk_level: str | None
    secret_value_redaction_flag: bool
    correlation_group_id: str | None = None
    location_file: str | None = None
    location_line_start: int | None = None
    location_line_end: int | None = None


@dataclass(frozen=True)
class SecurityResultView:
    """A read-only projection of the frozen Analysis, once `status = completed`
    -- Data_Contracts.md's Security Result contract, as seen from outside
    Sentinel Core. `None` if the Analysis hasn't reached a verdict yet.
    """

    analysis_id: str
    correlation_id: str
    findings: tuple[FindingView, ...]
    security_score: float
    policy_version_id: str
    verdict: VerdictValue
    triggered_rules: tuple[str, ...]
    completed_at: str
    degradation_any_scanner_failed: bool
    degradation_ai_available_at_completion: bool


class SecurityResultQueryPort(Protocol):
    def get(self, analysis_id: str) -> SecurityResultView | None:
        """Returns None if the Analysis doesn't exist or hasn't completed --
        never a partially-filled view of an in-progress Analysis.
        """
        ...
