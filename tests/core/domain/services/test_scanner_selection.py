"""Proves Scanner Selection: enabled AND applicable, nothing else (QA-07)."""

from __future__ import annotations

from sentinel.core.domain.analysis.value_objects import Artifact
from sentinel.core.domain.services.scanner_selection import select_scanners


def test_selects_only_scanners_that_are_both_enabled_and_applicable() -> None:
    artifacts = (Artifact(path="app.py", type="source", change_kind="modified"),)

    selected = select_scanners(artifacts, enabled_scanners=("semgrep", "trivy", "checkov"))

    assert selected == ("semgrep",)  # trivy/checkov don't apply to 'source'; gitleaks wasn't enabled


def test_a_scanner_enabled_but_not_applicable_is_never_selected() -> None:
    artifacts = (Artifact(path="app.py", type="source", change_kind="modified"),)

    selected = select_scanners(artifacts, enabled_scanners=("checkov",))

    assert selected == ()


def test_a_scanner_applicable_but_not_enabled_is_never_selected() -> None:
    artifacts = (Artifact(path="Dockerfile", type="dockerfile", change_kind="added"),)

    selected = select_scanners(artifacts, enabled_scanners=("semgrep",))

    assert selected == ()


def test_wildcard_applicability_matches_any_artifact_type() -> None:
    artifacts = (Artifact(path="config.yaml", type="other", change_kind="added"),)

    selected = select_scanners(artifacts, enabled_scanners=("gitleaks",))

    assert selected == ("gitleaks",)


def test_adding_a_new_scanner_requires_only_a_new_mapping_entry() -> None:
    """Proves QA-07: no existing caller code needs to change to add a scanner."""
    artifacts = (Artifact(path="infra/main.tf", type="terraform", change_kind="modified"),)
    custom_applicability = {"tfsec": ("terraform",)}

    selected = select_scanners(artifacts, enabled_scanners=("tfsec",), scanner_applicability=custom_applicability)

    assert selected == ("tfsec",)
