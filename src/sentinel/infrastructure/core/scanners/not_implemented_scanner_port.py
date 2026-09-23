"""Placeholder ScannerPort for the window between Phase 4 and Phase 5.

Never imported by tests (which use tests/fakes/FakeScannerPort instead) --
this is a *production* placeholder, so that composition.py can wire a
complete, real pipeline today without a single real scanner adapter yet.
Every scanner reports 'failed' rather than raising, so the Orchestrator's
existing degradation path (P-09/QA-03) produces a real, honest verdict
based on zero available findings -- never a hang, never a fabricated
success. It is replaced by real adapters (Semgrep, Bandit, Trivy,
Gitleaks, Checkov) in Phase 5 with no change to the Orchestrator.
"""

from __future__ import annotations

from sentinel.core.domain.analysis.value_objects import Artifact
from sentinel.core.ports.scanner_port import ScannerPort, ScannerRunResult


class NotYetImplementedScannerPort(ScannerPort):
    def run(
        self, scanner_id: str, scanner_version: str, timeout_seconds: int, artifacts: tuple[Artifact, ...]
    ) -> ScannerRunResult:
        return ScannerRunResult(
            status="failed",
            failure_note=f"scanner adapter for {scanner_id!r} is not implemented yet (Phase 5)",
        )
