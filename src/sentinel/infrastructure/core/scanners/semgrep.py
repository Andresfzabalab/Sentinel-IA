"""Semgrep adapter -- SAST for source code and GitHub Actions workflows
(docs/00_Product/MVP.md, Technology_Strategy.md).

`parse_semgrep_output` is the P-05 boundary: the only place Semgrep's
native JSON shape is ever read. Golden-fixture tested independently of
the subprocess invocation (Testing_Strategy.md's Scanner Adapter Tests).
"""

from __future__ import annotations

from typing import Any

from sentinel.core.domain.analysis.value_objects import Artifact
from sentinel.core.ports.scanner_port import NormalizedFindingData, ScannerRunResult
from sentinel.infrastructure.core.scanners.json_scanner_adapter import run_and_parse_json_scanner

_SEVERITY_MAP = {"ERROR": "critical", "WARNING": "high", "INFO": "low"}


def parse_semgrep_output(raw: dict[str, Any] | None) -> tuple[NormalizedFindingData, ...]:
    if not raw:
        return ()

    findings = []
    for result in raw.get("results", []):
        extra = result.get("extra", {})
        start = result.get("start", {})
        end = result.get("end", {})
        severity = str(extra.get("severity", "INFO")).upper()

        findings.append(
            NormalizedFindingData(
                category="sast",
                artifact_path=result["path"],
                artifact_type="source",
                rule_or_check_id=result["check_id"],
                severity_level=_SEVERITY_MAP.get(severity, "medium"),
                severity_raw_value=severity,
                location_file=result["path"],
                location_line_start=start.get("line"),
                location_line_end=end.get("line"),
            )
        )
    return tuple(findings)


class SemgrepAdapter:
    scanner_id = "semgrep"

    def run(
        self, scanner_id: str, scanner_version: str, timeout_seconds: int,
        artifacts: tuple[Artifact, ...], working_directory: str = "",
    ) -> ScannerRunResult:
        command = ["semgrep", "--config=auto", "--json", "--quiet", working_directory or "."]
        return run_and_parse_json_scanner(
            command, cwd=working_directory, timeout_seconds=timeout_seconds, parse=parse_semgrep_output,
        )
