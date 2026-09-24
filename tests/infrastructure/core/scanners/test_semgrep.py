"""Golden-fixture test for Semgrep's P-05 translation boundary, plus the
adapter's command-building and subprocess wiring.
"""

from __future__ import annotations

from unittest.mock import patch

from sentinel.infrastructure.core.scanners.json_scanner_adapter import run_and_parse_json_scanner
from sentinel.infrastructure.core.scanners.semgrep import SemgrepAdapter, parse_semgrep_output
from sentinel.infrastructure.core.scanners.subprocess_runner import SubprocessOutcome

_NATIVE_OUTPUT = {
    "results": [
        {
            "check_id": "python.lang.security.audit.sql-injection",
            "path": "app/db.py",
            "start": {"line": 42, "col": 5},
            "end": {"line": 42, "col": 60},
            "extra": {"severity": "ERROR", "message": "Possible SQL injection"},
        },
        {
            "check_id": "python.lang.best-practice.unused-import",
            "path": "app/utils.py",
            "start": {"line": 3, "col": 1},
            "end": {"line": 3, "col": 20},
            "extra": {"severity": "INFO", "message": "Unused import"},
        },
    ],
    "errors": [],
}


def test_parses_native_output_into_normalized_findings() -> None:
    findings = parse_semgrep_output(_NATIVE_OUTPUT)

    assert len(findings) == 2
    critical = findings[0]
    assert critical.category == "sast"
    assert critical.artifact_path == "app/db.py"
    assert critical.rule_or_check_id == "python.lang.security.audit.sql-injection"
    assert critical.severity_level == "critical"
    assert critical.severity_raw_value == "ERROR"
    assert critical.location_line_start == 42

    info = findings[1]
    assert info.severity_level == "low"


def test_empty_results_yields_no_findings() -> None:
    assert parse_semgrep_output({"results": [], "errors": []}) == ()
    assert parse_semgrep_output(None) == ()


def test_adapter_builds_expected_command_and_wires_the_parser() -> None:
    with patch(
        "sentinel.infrastructure.core.scanners.json_scanner_adapter.run_scanner_subprocess",
        return_value=SubprocessOutcome(status="succeeded", exit_code=0, stdout='{"results": [], "errors": []}', stderr=""),
    ) as mock_run:
        result = SemgrepAdapter().run("semgrep", "1.70.0", 120, artifacts=(), working_directory="/tmp/checkout")

    assert result.status == "succeeded"
    command = mock_run.call_args.args[0]
    assert command[0] == "semgrep"
    assert "/tmp/checkout" in command
    kwargs = mock_run.call_args.kwargs
    assert kwargs["cwd"] == "/tmp/checkout"
    assert kwargs["timeout_seconds"] == 120


def test_adapter_never_raises_when_run_and_parse_json_scanner_is_used(monkeypatch) -> None:
    """Sanity check that SemgrepAdapter.run truly delegates failure handling
    -- see test_json_scanner_adapter.py for the exhaustive failure cases."""
    result = run_and_parse_json_scanner(
        ["definitely-not-a-real-binary-xyz"], cwd="", timeout_seconds=5, parse=parse_semgrep_output
    )
    assert result.status == "failed"
