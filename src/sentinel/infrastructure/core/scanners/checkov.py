"""Checkov adapter -- broad multi-framework IaC/Kubernetes coverage
(Technology_Strategy.md).
"""

from __future__ import annotations

from typing import Any

from sentinel.core.domain.analysis.value_objects import Artifact
from sentinel.core.ports.scanner_port import NormalizedFindingData, ScannerRunResult
from sentinel.infrastructure.core.scanners.json_scanner_adapter import run_and_parse_json_scanner

_SEVERITY_MAP = {"CRITICAL": "critical", "HIGH": "high", "MEDIUM": "medium", "LOW": "low"}


def _map_severity(severity: str | None) -> str:
    if not severity:
        return "medium"  # Checkov doesn't always assign one; a failed check is still meaningful
    return _SEVERITY_MAP.get(str(severity).upper(), "medium")


def _infer_artifact_type(path: str) -> str:
    lower = path.lower()
    if "dockerfile" in lower:
        return "dockerfile"
    if lower.endswith(".tf"):
        return "terraform"
    if lower.endswith((".yaml", ".yml")):
        return "k8s-helm"
    return "other"


def parse_checkov_output(raw: dict[str, Any] | None) -> tuple[NormalizedFindingData, ...]:
    if not raw:
        return ()

    # Checkov's `-o json` nests everything under "results"; tolerate a bare
    # dict too, in case a future/different invocation flattens it.
    results = raw.get("results", raw)

    findings = []
    for check in results.get("failed_checks", []) or []:
        file_path = check.get("file_path", "")
        line_range = check.get("file_line_range") or [None, None]

        findings.append(
            NormalizedFindingData(
                category="iac",
                artifact_path=file_path,
                artifact_type=_infer_artifact_type(file_path),
                rule_or_check_id=check.get("check_id", "unknown"),
                severity_level=_map_severity(check.get("severity")),
                severity_raw_value=check.get("severity"),
                location_file=file_path,
                location_line_start=line_range[0] if len(line_range) > 0 else None,
                location_line_end=line_range[1] if len(line_range) > 1 else None,
            )
        )
    return tuple(findings)


class CheckovAdapter:
    scanner_id = "checkov"

    def run(
        self, scanner_id: str, scanner_version: str, timeout_seconds: int,
        artifacts: tuple[Artifact, ...], working_directory: str = "",
    ) -> ScannerRunResult:
        command = ["checkov", "-d", working_directory or ".", "-o", "json", "--quiet"]
        return run_and_parse_json_scanner(
            command, cwd=working_directory, timeout_seconds=timeout_seconds, parse=parse_checkov_output,
        )
