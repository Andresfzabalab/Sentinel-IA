"""Golden-fixture test for Trivy's P-05 translation boundary -- covers
both dependency vulnerabilities (SCA) and Dockerfile misconfigurations
(container) in one native output shape.
"""

from __future__ import annotations

from sentinel.infrastructure.core.scanners.trivy import parse_trivy_output

_NATIVE_OUTPUT = {
    "Results": [
        {
            "Target": "requirements.txt",
            "Class": "lang-pkgs",
            "Vulnerabilities": [
                {"VulnerabilityID": "CVE-2024-12345", "PkgName": "requests", "Severity": "HIGH"},
            ],
        },
        {
            "Target": "Dockerfile",
            "Class": "config",
            "Misconfigurations": [
                {
                    "ID": "AVD-DS-0002",
                    "Severity": "CRITICAL",
                    "CauseMetadata": {"StartLine": 3, "EndLine": 3},
                }
            ],
        },
    ]
}


def test_parses_vulnerabilities_and_misconfigurations() -> None:
    findings = parse_trivy_output(_NATIVE_OUTPUT)

    assert len(findings) == 2

    vuln = findings[0]
    assert vuln.category == "sca"
    assert vuln.artifact_path == "requirements.txt"
    assert vuln.rule_or_check_id == "CVE-2024-12345"
    assert vuln.severity_level == "high"

    misconfig = findings[1]
    assert misconfig.category == "container"
    assert misconfig.artifact_path == "Dockerfile"
    assert misconfig.rule_or_check_id == "AVD-DS-0002"
    assert misconfig.severity_level == "critical"
    assert misconfig.location_line_start == 3


def test_empty_results_yields_no_findings() -> None:
    assert parse_trivy_output({"Results": []}) == ()
    assert parse_trivy_output(None) == ()


def test_missing_vulnerabilities_and_misconfigurations_keys_are_tolerated() -> None:
    """A clean target reports neither key, or reports null instead of an
    empty list -- both must be handled without raising."""
    raw = {"Results": [{"Target": "clean.tf"}, {"Target": "also_clean.tf", "Vulnerabilities": None}]}

    assert parse_trivy_output(raw) == ()
