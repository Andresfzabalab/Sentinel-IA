"""Proves CompositeScannerPort dispatches by scanner_id and degrades
honestly (never raises) for an unregistered scanner_id (QA-07)."""

from __future__ import annotations

from sentinel.core.ports.scanner_port import ScannerRunResult
from sentinel.infrastructure.core.scanners.composite_scanner_port import CompositeScannerPort


class _StubAdapter:
    def __init__(self, result: ScannerRunResult) -> None:
        self._result = result
        self.calls = []

    def run(self, scanner_id, scanner_version, timeout_seconds, artifacts, working_directory=""):
        self.calls.append((scanner_id, scanner_version, timeout_seconds, working_directory))
        return self._result


def test_dispatches_to_the_registered_adapter_for_the_given_scanner_id() -> None:
    stub = _StubAdapter(ScannerRunResult(status="succeeded", exit_code=0))
    port = CompositeScannerPort({"my-tool": stub})

    result = port.run("my-tool", "1.0", 60, artifacts=(), working_directory="/tmp/x")

    assert result.status == "succeeded"
    assert stub.calls == [("my-tool", "1.0", 60, "/tmp/x")]


def test_unregistered_scanner_id_degrades_to_failed_never_raises() -> None:
    port = CompositeScannerPort({})

    result = port.run("nonexistent-scanner", "1.0", 60, artifacts=())

    assert result.status == "failed"
    assert "nonexistent-scanner" in result.failure_note


def test_default_adapters_include_all_five_mvp_scanners() -> None:
    from sentinel.infrastructure.core.scanners.composite_scanner_port import DEFAULT_ADAPTERS

    assert set(DEFAULT_ADAPTERS.keys()) == {"semgrep", "bandit", "trivy", "gitleaks", "checkov"}
