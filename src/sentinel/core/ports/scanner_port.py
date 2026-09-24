"""ScannerPort -- Infrastructure port to the Security Scanner Execution
container (docs/02_Domain/Ports_and_Interfaces.md).

Each real adapter (Semgrep, Bandit, Trivy, Gitleaks, Checkov -- Phase 5) is
solely responsible for translating its native output into the
NormalizedFindingData shape below (P-05); no component outside the Scanner
context ever sees a scanner's native format. Phase 3 exercises the
Orchestrator against a Fake implementation of this same interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sentinel.core.domain.analysis.value_objects import Artifact, RiskLevel


@dataclass(frozen=True)
class NormalizedFindingData:
    """Everything needed to construct a domain Finding, once a scanner
    execution succeeds -- already normalized (P-05), never a native format.
    """

    category: str
    artifact_path: str
    artifact_type: str
    rule_or_check_id: str
    severity_level: RiskLevel
    severity_raw_value: str | None = None
    location_file: str | None = None
    location_line_start: int | None = None
    location_line_end: int | None = None
    secret_value_redaction_flag: bool = False


@dataclass(frozen=True)
class ScannerRunResult:
    status: str  # 'succeeded' | 'failed' | 'timed_out'
    exit_code: int | None = None
    failure_note: str | None = None
    findings: tuple[NormalizedFindingData, ...] = ()


class ScannerPort(Protocol):
    def run(
        self,
        scanner_id: str,
        scanner_version: str,
        timeout_seconds: int,
        artifacts: tuple[Artifact, ...],
        working_directory: str = "",
    ) -> ScannerRunResult:
        """Must never raise for an ordinary scanner failure/timeout/crash --
        those are represented as a `ScannerRunResult` with status 'failed'
        or 'timed_out' (P-09). Only a genuine adapter bug should raise.

        `working_directory` points to a local directory containing the
        actual checked-out files a real scanner binary needs to read --
        added in Phase 5 since static analysis tools fundamentally require
        real file content, not just the `Artifact` metadata (path/type).
        Populating it with a real PR checkout is Phase 6 work
        (Implementation_Strategy.md); Phase 5 adapters must degrade to a
        'failed' result honestly when it is empty or missing, never hang
        or fabricate findings.
        """
        ...
