"""Artifact Classification Service.

Per docs/02_Domain/Domain_Services.md: reads configured classification
rules (path/extension patterns -> Artifact type mapping), takes changed
file paths, and returns Artifact values -- this output *becomes*
Analysis's ArtifactList once written at T1; the service builds that list,
it does not read it as a pre-existing input. Invariant: every changed file
gets exactly one type before scanner selection runs.
"""

from __future__ import annotations

from dataclasses import dataclass

from sentinel.core.domain.analysis.value_objects import Artifact, ArtifactType, ChangeKind

_DEPENDENCY_MANIFEST_NAMES = frozenset({"requirements.txt", "package.json", "package-lock.json", "poetry.lock"})
_SOURCE_EXTENSIONS = frozenset({".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rb"})
_TERRAFORM_EXTENSIONS = frozenset({".tf", ".tfvars"})
_YAML_EXTENSIONS = frozenset({".yaml", ".yml"})


@dataclass(frozen=True)
class ChangedFile:
    path: str
    change_kind: ChangeKind


def classify_artifact_type(path: str) -> ArtifactType:
    """Deterministic, rule-based classification -- no I/O, no ambiguity: one
    file always maps to exactly one type.
    """
    normalized = path.replace("\\", "/")
    filename = normalized.rsplit("/", 1)[-1]
    lower = normalized.lower()

    if ".github/workflows/" in lower and (lower.endswith(".yml") or lower.endswith(".yaml")):
        return "github-actions"

    if filename == "Dockerfile" or filename.startswith("Dockerfile.") or lower.endswith("/dockerfile"):
        return "dockerfile"

    if filename in _DEPENDENCY_MANIFEST_NAMES:
        return "dependency-manifest"

    if any(lower.endswith(ext) for ext in _TERRAFORM_EXTENSIONS):
        return "terraform"

    if ("helm" in lower or "k8s" in lower or "kubernetes" in lower) and any(
        lower.endswith(ext) for ext in _YAML_EXTENSIONS
    ):
        return "k8s-helm"

    if any(lower.endswith(ext) for ext in _SOURCE_EXTENSIONS):
        return "source"

    return "other"


def classify_artifacts(changed_files: tuple[ChangedFile, ...]) -> tuple[Artifact, ...]:
    return tuple(
        Artifact(path=cf.path, type=classify_artifact_type(cf.path), change_kind=cf.change_kind)
        for cf in changed_files
    )
