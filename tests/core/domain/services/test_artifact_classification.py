"""Proves Artifact Classification: every changed file gets exactly one type."""

from __future__ import annotations

from sentinel.core.domain.services.artifact_classification import (
    ChangedFile,
    classify_artifact_type,
    classify_artifacts,
)


def test_classifies_common_artifact_types() -> None:
    assert classify_artifact_type("app/main.py") == "source"
    assert classify_artifact_type("Dockerfile") == "dockerfile"
    assert classify_artifact_type("services/api/Dockerfile") == "dockerfile"
    assert classify_artifact_type("infra/main.tf") == "terraform"
    assert classify_artifact_type(".github/workflows/ci.yml") == "github-actions"
    assert classify_artifact_type("requirements.txt") == "dependency-manifest"
    assert classify_artifact_type("package.json") == "dependency-manifest"
    assert classify_artifact_type("charts/helm/values.yaml") == "k8s-helm"
    assert classify_artifact_type("README.md") == "other"


def test_classify_artifacts_preserves_change_kind_and_produces_one_artifact_per_file() -> None:
    changed = (
        ChangedFile(path="app.py", change_kind="modified"),
        ChangedFile(path="Dockerfile", change_kind="added"),
        ChangedFile(path="old_module.py", change_kind="deleted"),
    )

    artifacts = classify_artifacts(changed)

    assert len(artifacts) == 3
    assert artifacts[0].type == "source" and artifacts[0].change_kind == "modified"
    assert artifacts[1].type == "dockerfile" and artifacts[1].change_kind == "added"
    assert artifacts[2].change_kind == "deleted"


def test_classification_is_deterministic() -> None:
    assert classify_artifact_type("app/main.py") == classify_artifact_type("app/main.py")
