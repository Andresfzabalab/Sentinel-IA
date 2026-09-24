"""Golden-fixture test for Gitleaks' P-05 translation boundary --
security-critical: the raw secret value must never appear anywhere in a
NormalizedFindingData, per Input_Output_Model.md's redaction rule.
"""

from __future__ import annotations

import dataclasses

from sentinel.infrastructure.core.scanners.gitleaks import parse_gitleaks_output

_RAW_SECRET_VALUE = "sk-supersecretapikeyvalue1234567890"

_NATIVE_OUTPUT = [
    {
        "Description": "AWS Access Key",
        "File": "config/settings.py",
        "StartLine": 12,
        "EndLine": 12,
        "RuleID": "aws-access-key",
        "Secret": _RAW_SECRET_VALUE,
    }
]


def test_parses_native_output_into_normalized_findings() -> None:
    findings = parse_gitleaks_output(_NATIVE_OUTPUT)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.category == "secret"
    assert finding.artifact_path == "config/settings.py"
    assert finding.rule_or_check_id == "aws-access-key"
    assert finding.severity_level == "critical"
    assert finding.location_line_start == 12
    assert finding.secret_value_redaction_flag is True


def test_the_raw_secret_value_never_appears_anywhere_in_the_normalized_finding() -> None:
    """The direct, automated proof of Input_Output_Model.md's redaction
    rule at the parsing boundary -- not just a documented claim."""
    findings = parse_gitleaks_output(_NATIVE_OUTPUT)

    finding_repr = repr(dataclasses.asdict(findings[0]))

    assert _RAW_SECRET_VALUE not in finding_repr


def test_empty_or_missing_output_yields_no_findings() -> None:
    assert parse_gitleaks_output([]) == ()
    assert parse_gitleaks_output(None) == ()


def test_every_gitleaks_finding_is_always_critical_severity() -> None:
    """A leaked credential is always unconditionally high-priority,
    regardless of what Gitleaks itself would otherwise report."""
    raw = [{"File": "a.py", "RuleID": "generic-secret", "StartLine": 1, "EndLine": 1, "Secret": "x"}]

    findings = parse_gitleaks_output(raw)

    assert findings[0].severity_level == "critical"
