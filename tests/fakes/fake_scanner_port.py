"""FakeScannerPort -- the one reusable in-memory implementation of
ScannerPort used across unit and application-layer tests. Scriptable per
scanner_id; records every call made so a test can assert on invocation
order/arguments if needed.

Thread-safe since Phase 6: the Orchestrator now runs scanners concurrently
via a ThreadPoolExecutor, including against this Fake in tests.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from sentinel.core.domain.analysis.value_objects import Artifact
from sentinel.core.ports.scanner_port import ScannerPort, ScannerRunResult


@dataclass
class RecordedRun:
    scanner_id: str
    scanner_version: str
    timeout_seconds: int
    artifacts: tuple[Artifact, ...]
    working_directory: str = ""


class FakeScannerPort(ScannerPort):
    def __init__(self) -> None:
        self._results: dict[str, ScannerRunResult] = {}
        self._delays: dict[str, float] = {}
        self._default_result = ScannerRunResult(status="succeeded", exit_code=0, findings=())
        self.calls: list[RecordedRun] = []
        self._calls_lock = threading.Lock()

    def script_result(self, scanner_id: str, result: ScannerRunResult) -> None:
        self._results[scanner_id] = result

    def script_delay(self, scanner_id: str, delay_seconds: float) -> None:
        """Lets a test force real thread interleaving (Phase 6's concurrent
        scanner completion tests) without depending on timing luck.
        """
        self._delays[scanner_id] = delay_seconds

    def run(
        self,
        scanner_id: str,
        scanner_version: str,
        timeout_seconds: int,
        artifacts: tuple[Artifact, ...],
        working_directory: str = "",
    ) -> ScannerRunResult:
        with self._calls_lock:
            self.calls.append(RecordedRun(scanner_id, scanner_version, timeout_seconds, artifacts, working_directory))

        delay = self._delays.get(scanner_id)
        if delay:
            time.sleep(delay)

        return self._results.get(scanner_id, self._default_result)
