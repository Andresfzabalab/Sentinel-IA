"""Golden-fixture test for Bandit's P-05 translation boundary."""

from __future__ import annotations

from unittest.mock import patch

from sentinel.infrastructure.core.scanners.bandit import BanditAdapter, parse_bandit_output
from sentinel.infrastructure.core.scanners.subprocess_runner import SubprocessOutcome

_NATIVE_OUTPUT = {
    "results": [
        {
            "filename": "app/auth.py",
            "test_id": "B105",
            "issue_severity": "HIGH",
            "issue_confidence": "MEDIUM",
            "line_number": 17,
            "issue_text": "Possible hardcoded password",
        }
    ]
}


def test_parses_native_output_into_normalized_findings() -> None:
    findings = parse_bandit_output(_NATIVE_OUTPUT)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.category == "sast"
    assert finding.artifact_path == "app/auth.py"
    assert finding.rule_or_check_id == "B105"
    assert finding.severity_level == "high"
    assert finding.location_line_start == 17
    assert finding.location_line_end == 17


def test_empty_results_yields_no_findings() -> None:
    assert parse_bandit_output({"results": []}) == ()
    assert parse_bandit_output(None) == ()


def test_adapter_builds_expected_command() -> None:
    with patch(
        "sentinel.infrastructure.core.scanners.json_scanner_adapter.run_scanner_subprocess",
        return_value=SubprocessOutcome(status="succeeded", exit_code=1, stdout='{"results": []}', stderr=""),
    ) as mock_run:
        result = BanditAdapter().run("bandit", "1.7.0", 60, artifacts=(), working_directory="/tmp/checkout")

    # Bandit exits 1 when issues are found -- that must still read as a
    # successful scan, not a crash.
    assert result.status == "succeeded"
    command = mock_run.call_args.args[0]
    assert command[0] == "bandit"
    assert "/tmp/checkout" in command
