"""FakeScannerPort -- the one reusable in-memory implementation of
ScannerPort used across unit and application-layer tests. Scriptable per
scanner_id; records every call made so a test can assert on invocation
order/arguments if needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sentinel.core.domain.analysis.value_objects import Artifact
from sentinel.core.ports.scanner_port import ScannerPort, ScannerRunResult


@dataclass
class RecordedRun:
    scanner_id: str
    scanner_version: str
    timeout_seconds: int
    artifacts: tuple[Artifact, ...]


class FakeScannerPort(ScannerPort):
    def __init__(self) -> None:
        self._results: dict[str, ScannerRunResult] = {}
        self._default_result = ScannerRunResult(status="succeeded", exit_code=0, findings=())
        self.calls: list[RecordedRun] = []

    def script_result(self, scanner_id: str, result: ScannerRunResult) -> None:
        self._results[scanner_id] = result

    def run(
        self, scanner_id: str, scanner_version: str, timeout_seconds: int, artifacts: tuple[Artifact, ...]
    ) -> ScannerRunResult:
        self.calls.append(RecordedRun(scanner_id, scanner_version, timeout_seconds, artifacts))
        return self._results.get(scanner_id, self._default_result)
