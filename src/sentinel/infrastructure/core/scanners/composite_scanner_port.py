"""CompositeScannerPort -- the real ScannerPort implementation wired into
composition.py, dispatching to the per-tool adapter by scanner_id.

Adding a new scanner (QA-07) means registering one more entry in
DEFAULT_ADAPTERS -- no change to the Orchestrator, Risk, or Policy code.
"""

from __future__ import annotations

from sentinel.core.domain.analysis.value_objects import Artifact
from sentinel.core.ports.scanner_port import ScannerPort, ScannerRunResult
from sentinel.infrastructure.core.scanners.bandit import BanditAdapter
from sentinel.infrastructure.core.scanners.checkov import CheckovAdapter
from sentinel.infrastructure.core.scanners.gitleaks import GitleaksAdapter
from sentinel.infrastructure.core.scanners.semgrep import SemgrepAdapter
from sentinel.infrastructure.core.scanners.trivy import TrivyAdapter

DEFAULT_ADAPTERS: dict[str, ScannerPort] = {
    "semgrep": SemgrepAdapter(),
    "bandit": BanditAdapter(),
    "trivy": TrivyAdapter(),
    "gitleaks": GitleaksAdapter(),
    "checkov": CheckovAdapter(),
}


class CompositeScannerPort:
    def __init__(self, adapters: dict[str, ScannerPort] | None = None) -> None:
        self._adapters = adapters if adapters is not None else DEFAULT_ADAPTERS

    def run(
        self,
        scanner_id: str,
        scanner_version: str,
        timeout_seconds: int,
        artifacts: tuple[Artifact, ...],
        working_directory: str = "",
    ) -> ScannerRunResult:
        adapter = self._adapters.get(scanner_id)
        if adapter is None:
            return ScannerRunResult(status="failed", failure_note=f"no adapter registered for scanner_id={scanner_id!r}")

        return adapter.run(scanner_id, scanner_version, timeout_seconds, artifacts, working_directory)
