"""Gitleaks adapter -- secret scanning (Technology_Strategy.md).

Security-critical parsing boundary: Gitleaks' native output includes the
actual detected secret value (`Secret`). Per Input_Output_Model.md's
redaction rule, that raw value must NEVER cross into a `NormalizedFinding`
-- this parser deliberately never reads that field into anything it
returns, and every finding it produces sets `secret_value_redaction_flag`.
A detected secret is always treated as `critical` severity, regardless of
what Gitleaks itself reports, since any leaked credential is an
unconditional high-priority issue.
"""

from __future__ import annotations

from typing import Any

from sentinel.core.domain.analysis.value_objects import Artifact
from sentinel.core.ports.scanner_port import NormalizedFindingData, ScannerRunResult
from sentinel.infrastructure.core.scanners.json_scanner_adapter import run_and_parse_json_scanner


def parse_gitleaks_output(raw: list[dict[str, Any]] | None) -> tuple[NormalizedFindingData, ...]:
    if not raw:
        return ()

    findings = []
    for item in raw:
        # Deliberately never reads item.get("Secret") -- see module docstring.
        findings.append(
            NormalizedFindingData(
                category="secret",
                artifact_path=item.get("File", ""),
                artifact_type="other",
                rule_or_check_id=item.get("RuleID", "unknown"),
                severity_level="critical",
                location_file=item.get("File"),
                location_line_start=item.get("StartLine"),
                location_line_end=item.get("EndLine"),
                secret_value_redaction_flag=True,
            )
        )
    return tuple(findings)


class GitleaksAdapter:
    scanner_id = "gitleaks"

    def run(
        self, scanner_id: str, scanner_version: str, timeout_seconds: int,
        artifacts: tuple[Artifact, ...], working_directory: str = "",
    ) -> ScannerRunResult:
        command = [
            "gitleaks", "detect",
            "--source", working_directory or ".",
            "--no-git",
            "--report-format", "json",
            "--report-path", "-",
            "--exit-code", "0",
        ]
        return run_and_parse_json_scanner(
            command, cwd=working_directory, timeout_seconds=timeout_seconds,
            parse=parse_gitleaks_output, empty_output_value=[],
        )
