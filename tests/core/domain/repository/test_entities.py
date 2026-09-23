"""Proves a Repository must always have a Policy assigned (Entities_Value_Objects.md)."""

from __future__ import annotations

import pytest

from sentinel.core.domain.exceptions import RepositoryMissingPolicy
from sentinel.core.domain.repository.entities import Repository


def _repository(**overrides) -> Repository:
    defaults = dict(
        id="repo-1", external_identifier="acme/widgets", assigned_policy_id="policy-1",
        created_at="t0", updated_at="t0",
    )
    defaults.update(overrides)
    return Repository(**defaults)


def test_cannot_construct_a_repository_without_a_policy() -> None:
    with pytest.raises(RepositoryMissingPolicy):
        _repository(assigned_policy_id="")


def test_update_configuration_never_removes_the_policy_assignment() -> None:
    repo = _repository()

    with pytest.raises(RepositoryMissingPolicy):
        repo.update_configuration(assigned_policy_id="", updated_at="t1")

    assert repo.assigned_policy_id == "policy-1"


def test_update_configuration_applies_only_the_provided_fields() -> None:
    repo = _repository(enabled_scanners=("semgrep",))

    repo.update_configuration(enabled_scanners=("semgrep", "gitleaks"), updated_at="t1")

    assert repo.enabled_scanners == ("semgrep", "gitleaks")
    assert repo.assigned_policy_id == "policy-1"  # unchanged
    assert repo.updated_at == "t1"


def test_a_mid_flight_config_change_does_not_retroactively_touch_anything_else() -> None:
    """This is really just proving update_configuration mutates in place --
    the 'does not affect an in-flight Analysis' guarantee lives in the
    Orchestrator (Phase 3), which reads config once at T1."""
    repo = _repository()
    original_created_at = repo.created_at

    repo.update_configuration(active=False, updated_at="t1")

    assert repo.created_at == original_created_at
    assert repo.active is False
