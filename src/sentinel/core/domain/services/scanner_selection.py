"""Scanner Selection Service (Strategy pattern).

Per docs/02_Domain/Domain_Services.md: reads the Repository Aggregate's
`enabled_scanners` and the Analysis's ArtifactList, and selects a scanner
only if it is both enabled for the Repository AND applicable to at least
one Artifact's type (QA-07). Adding a scanner requires zero changes to
Orchestrator, Risk, or Policy code -- only an entry in this mapping (and,
later, a new adapter).
"""

from __future__ import annotations

from sentinel.core.domain.analysis.value_objects import Artifact, ArtifactType

# "*" means the scanner applies to every artifact type (e.g. secret scanning).
DEFAULT_SCANNER_APPLICABILITY: dict[str, tuple[ArtifactType, ...] | str] = {
    "semgrep": ("source", "github-actions"),
    "bandit": ("source",),
    "trivy": ("dockerfile", "dependency-manifest"),
    "gitleaks": "*",
    "checkov": ("dockerfile", "k8s-helm", "terraform"),
}


def select_scanners(
    artifacts: tuple[Artifact, ...],
    enabled_scanners: tuple[str, ...],
    scanner_applicability: dict[str, tuple[ArtifactType, ...] | str] | None = None,
) -> tuple[str, ...]:
    applicability = scanner_applicability if scanner_applicability is not None else DEFAULT_SCANNER_APPLICABILITY
    artifact_types = {artifact.type for artifact in artifacts}

    selected: list[str] = []
    for scanner_id in enabled_scanners:
        applies_to = applicability.get(scanner_id)
        if applies_to is None:
            continue
        if applies_to == "*" or artifact_types.intersection(applies_to):
            selected.append(scanner_id)

    return tuple(selected)
