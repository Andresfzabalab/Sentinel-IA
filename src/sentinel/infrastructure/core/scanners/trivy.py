"""Trivy adapter -- covers both SCA (dependency vulnerabilities) and
container/IaC misconfigurations in one tool (Technology_Strategy.md).
"""

from __future__ import annotations

from typing import Any

from sentinel.core.domain.analysis.value_objects import Artifact
from sentinel.core.ports.scanner_port import NormalizedFindingData, ScannerRunResult
from sentinel.infrastructure.core.scanners.json_scanner_adapter import run_and_parse_json_scanner

_SEVERITY_MAP = {"CRITICAL": "critical", "HIGH": "high", "MEDIUM": "medium", "LOW": "low"}


def _map_severity(severity: str | None) -> str:
    return _SEVERITY_MAP.get(str(severity or "").upper(), "medium")


def parse_trivy_output(raw: dict[str, Any] | None) -> tuple[NormalizedFindingData, ...]:
    if not raw:
        return ()

    findings = []
    for result in raw.get("Results", []) or []:
        target = result.get("Target", "")

        for vuln in result.get("Vulnerabilities", []) or []:
            findings.append(
                NormalizedFindingData(
                    category="sca",
                    artifact_path=target,
                    artifact_type="dependency-manifest",
                    rule_or_check_id=vuln.get("VulnerabilityID", "unknown"),
                    severity_level=_map_severity(vuln.get("Severity")),
                    severity_raw_value=vuln.get("Severity"),
                )
            )

        for misconfig in result.get("Misconfigurations", []) or []:
            cause = misconfig.get("CauseMetadata") or {}
            findings.append(
                NormalizedFindingData(
                    category="container",
                    artifact_path=target,
                    artifact_type="dockerfile",
                    rule_or_check_id=misconfig.get("ID", "unknown"),
                    severity_level=_map_severity(misconfig.get("Severity")),
                    severity_raw_value=misconfig.get("Severity"),
                    location_file=target,
                    location_line_start=cause.get("StartLine"),
                    location_line_end=cause.get("EndLine"),
                )
            )

    return tuple(findings)


class TrivyAdapter:
    scanner_id = "trivy"

    def run(
        self, scanner_id: str, scanner_version: str, timeout_seconds: int,
        artifacts: tuple[Artifact, ...], working_directory: str = "",
    ) -> ScannerRunResult:
        command = ["trivy", "fs", "--format", "json", "--quiet", working_directory or "."]
        return run_and_parse_json_scanner(
            command, cwd=working_directory, timeout_seconds=timeout_seconds, parse=parse_trivy_output,
        )
