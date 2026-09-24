"""Proves the shared run-subprocess-then-parse-JSON flow: subprocess
outcomes pass through untouched when not 'succeeded'; malformed JSON and
an unexpected output shape both degrade to 'failed' rather than raising.
"""

from __future__ import annotations

from unittest.mock import patch

from sentinel.core.ports.scanner_port import NormalizedFindingData
from sentinel.infrastructure.core.scanners.json_scanner_adapter import run_and_parse_json_scanner
from sentinel.infrastructure.core.scanners.subprocess_runner import SubprocessOutcome


def _fake_finding() -> NormalizedFindingData:
    return NormalizedFindingData(
        category="sast", artifact_path="app.py", artifact_type="source",
        rule_or_check_id="r1", severity_level="high",
    )


def test_a_timed_out_subprocess_outcome_passes_through_without_parsing() -> None:
    with patch(
        "sentinel.infrastructure.core.scanners.json_scanner_adapter.run_scanner_subprocess",
        return_value=SubprocessOutcome(status="timed_out", exit_code=None, stdout="", stderr="", failure_note="exceeded 5s timeout"),
    ):
        result = run_and_parse_json_scanner(["irrelevant"], cwd="", timeout_seconds=5, parse=lambda raw: (_fake_finding(),))

    assert result.status == "timed_out"
    assert result.findings == ()


def test_valid_json_is_parsed_into_findings() -> None:
    with patch(
        "sentinel.infrastructure.core.scanners.json_scanner_adapter.run_scanner_subprocess",
        return_value=SubprocessOutcome(status="succeeded", exit_code=0, stdout='{"results": []}', stderr=""),
    ):
        result = run_and_parse_json_scanner(
            ["irrelevant"], cwd="", timeout_seconds=5, parse=lambda raw: (_fake_finding(),)
        )

    assert result.status == "succeeded"
    assert result.findings == (_fake_finding(),)


def test_malformed_json_degrades_to_failed_never_raises() -> None:
    with patch(
        "sentinel.infrastructure.core.scanners.json_scanner_adapter.run_scanner_subprocess",
        return_value=SubprocessOutcome(status="succeeded", exit_code=0, stdout="{not valid json", stderr=""),
    ):
        result = run_and_parse_json_scanner(["irrelevant"], cwd="", timeout_seconds=5, parse=lambda raw: (_fake_finding(),))

    assert result.status == "failed"
    assert "JSON" in result.failure_note


def test_unexpected_shape_during_parse_degrades_to_failed_never_raises() -> None:
    def bad_parse(raw):
        return raw["this_key_does_not_exist"]

    with patch(
        "sentinel.infrastructure.core.scanners.json_scanner_adapter.run_scanner_subprocess",
        return_value=SubprocessOutcome(status="succeeded", exit_code=0, stdout='{"results": []}', stderr=""),
    ):
        result = run_and_parse_json_scanner(["irrelevant"], cwd="", timeout_seconds=5, parse=bad_parse)

    assert result.status == "failed"
    assert "shape" in result.failure_note.lower()


def test_empty_stdout_uses_the_provided_empty_output_value() -> None:
    with patch(
        "sentinel.infrastructure.core.scanners.json_scanner_adapter.run_scanner_subprocess",
        return_value=SubprocessOutcome(status="succeeded", exit_code=0, stdout="   ", stderr=""),
    ):
        result = run_and_parse_json_scanner(
            ["irrelevant"], cwd="", timeout_seconds=5, parse=lambda raw: () if raw == [] else (_fake_finding(),),
            empty_output_value=[],
        )

    assert result.status == "succeeded"
    assert result.findings == ()
