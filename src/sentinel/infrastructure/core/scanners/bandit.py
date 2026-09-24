"""Bandit adapter -- Python-specific SAST complement to Semgrep
(Technology_Strategy.md).
"""

from __future__ import annotations

from typing import Any

from sentinel.core.domain.analysis.value_objects import Artifact
from sentinel.core.ports.scanner_port import NormalizedFindingData, ScannerRunResult
from sentinel.infrastructure.core.scanners.json_scanner_adapter import run_and_parse_json_scanner

_SEVERITY_MAP = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"}


def parse_bandit_output(raw: dict[str, Any] | None) -> tuple[NormalizedFindingData, ...]:
    if not raw:
        return ()

    findings = []
    for result in raw.get("results", []):
        severity = str(result.get("issue_severity", "LOW")).upper()
        line = result.get("line_number")

        findings.append(
            NormalizedFindingData(
                category="sast",
                artifact_path=result["filename"],
                artifact_type="source",
                rule_or_check_id=result["test_id"],
                severity_level=_SEVERITY_MAP.get(severity, "low"),
                severity_raw_value=severity,
                location_file=result["filename"],
                location_line_start=line,
                location_line_end=line,
            )
        )
    return tuple(findings)


class BanditAdapter:
    scanner_id = "bandit"

    def run(
        self, scanner_id: str, scanner_version: str, timeout_seconds: int,
        artifacts: tuple[Artifact, ...], working_directory: str = "",
    ) -> ScannerRunResult:
        command = ["bandit", "-r", working_directory or ".", "-f", "json"]
        return run_and_parse_json_scanner(
            command, cwd=working_directory, timeout_seconds=timeout_seconds, parse=parse_bandit_output,
        )
