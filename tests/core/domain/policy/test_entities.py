"""Proves Policy Version immutability once published (QA-01)."""

from __future__ import annotations

import dataclasses

import pytest

from sentinel.core.domain.exceptions import DuplicatePolicyVersion
from sentinel.core.domain.policy.entities import Policy
from sentinel.core.domain.policy.value_objects import PolicyVersion


def test_publish_version_sets_current_version() -> None:
    policy = Policy(id="p-1", created_at="t0")

    policy.publish_version(PolicyVersion(id="p-1-v1", policy_id="p-1", version_number=1, rules={}, published_at="t0", published_by="a"))

    assert policy.current_version.id == "p-1-v1"


def test_publishing_a_new_version_never_edits_the_prior_one() -> None:
    policy = Policy(id="p-1", created_at="t0")
    policy.publish_version(
        PolicyVersion(id="v1", policy_id="p-1", version_number=1, rules={"blockOnSeverity": "high"}, published_at="t0", published_by="a")
    )
    policy.publish_version(
        PolicyVersion(id="v2", policy_id="p-1", version_number=2, rules={"blockOnSeverity": "critical"}, published_at="t1", published_by="a")
    )

    assert policy.get_version("v1").rules == {"blockOnSeverity": "high"}
    assert policy.get_version("v2").rules == {"blockOnSeverity": "critical"}
    assert policy.current_version.id == "v2"


def test_rejects_publishing_the_same_version_number_twice() -> None:
    policy = Policy(id="p-1", created_at="t0")
    policy.publish_version(PolicyVersion(id="v1", policy_id="p-1", version_number=1, rules={}, published_at="t0", published_by="a"))

    with pytest.raises(DuplicatePolicyVersion):
        policy.publish_version(PolicyVersion(id="v1-dup", policy_id="p-1", version_number=1, rules={}, published_at="t1", published_by="a"))

    assert policy.current_version.id == "v1"


def test_policy_version_is_immutable() -> None:
    version = PolicyVersion(id="v1", policy_id="p-1", version_number=1, rules={}, published_at="t0", published_by="a")

    with pytest.raises(dataclasses.FrozenInstanceError):
        version.version_number = 2
