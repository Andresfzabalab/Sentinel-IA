"""Golden-fixture test for Checkov's P-05 translation boundary."""

from __future__ import annotations

from sentinel.infrastructure.core.scanners.checkov import parse_checkov_output

_NATIVE_OUTPUT = {
    "results": {
        "failed_checks": [
            {
                "check_id": "CKV_K8S_8",
                "file_path": "k8s/deployment.yaml",
                "severity": "MEDIUM",
                "file_line_range": [10, 15],
            },
            {
                "check_id": "CKV_DOCKER_2",
                "file_path": "Dockerfile",
                "severity": None,
                "file_line_range": [1, 1],
            },
        ],
        "passed_checks": [{"check_id": "CKV_K8S_1", "file_path": "k8s/deployment.yaml"}],
    }
}


def test_parses_only_failed_checks_into_normalized_findings() -> None:
    findings = parse_checkov_output(_NATIVE_OUTPUT)

    assert len(findings) == 2
    k8s_finding = findings[0]
    assert k8s_finding.category == "iac"
    assert k8s_finding.artifact_type == "k8s-helm"
    assert k8s_finding.rule_or_check_id == "CKV_K8S_8"
    assert k8s_finding.severity_level == "medium"
    assert k8s_finding.location_line_start == 10
    assert k8s_finding.location_line_end == 15


def test_a_missing_severity_defaults_to_medium_rather_than_being_dropped() -> None:
    findings = parse_checkov_output(_NATIVE_OUTPUT)

    docker_finding = findings[1]
    assert docker_finding.artifact_type == "dockerfile"
    assert docker_finding.severity_level == "medium"


def test_tolerates_a_bare_results_dict_without_the_outer_wrapper() -> None:
    bare = {"failed_checks": [{"check_id": "CKV_1", "file_path": "main.tf", "severity": "HIGH"}]}

    findings = parse_checkov_output(bare)

    assert len(findings) == 1
    assert findings[0].artifact_type == "terraform"
    assert findings[0].severity_level == "high"


def test_empty_or_missing_output_yields_no_findings() -> None:
    assert parse_checkov_output({"results": {"failed_checks": []}}) == ()
    assert parse_checkov_output(None) == ()
