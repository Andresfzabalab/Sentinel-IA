"""Proves Policy Version immutability and duplicate-publish rejection (QA-01)."""

from __future__ import annotations

import pytest

from sentinel.infrastructure.core.sqlite.policy_store import (
    DuplicatePolicyVersion,
    PolicyCreate,
    PolicyVersionPublish,
    SqlitePolicyStore,
)


def test_publish_version_sets_current_version(sqlite_conn):
    store = SqlitePolicyStore(sqlite_conn)
    store.create_policy(PolicyCreate(id="p-1", created_at="t0"))

    store.publish_version(
        PolicyVersionPublish(id="p-1-v1", policy_id="p-1", version_number=1, rules="{}", published_at="t0", published_by="devsecops-1")
    )

    current = store.get_current_version("p-1")
    assert current["id"] == "p-1-v1"


def test_publishing_a_new_version_never_edits_the_prior_one(sqlite_conn):
    store = SqlitePolicyStore(sqlite_conn)
    store.create_policy(PolicyCreate(id="p-1", created_at="t0"))
    store.publish_version(
        PolicyVersionPublish(id="p-1-v1", policy_id="p-1", version_number=1, rules='{"blockOn": "high"}', published_at="t0", published_by="a")
    )
    store.publish_version(
        PolicyVersionPublish(id="p-1-v2", policy_id="p-1", version_number=2, rules='{"blockOn": "critical"}', published_at="t1", published_by="a")
    )

    v1 = store.get_policy_version("p-1-v1")
    v2 = store.get_policy_version("p-1-v2")
    assert v1["rules"] == '{"blockOn": "high"}'
    assert v2["rules"] == '{"blockOn": "critical"}'
    assert store.get_current_version("p-1")["id"] == "p-1-v2"


def test_rejects_publishing_the_same_version_number_twice(sqlite_conn):
    store = SqlitePolicyStore(sqlite_conn)
    store.create_policy(PolicyCreate(id="p-1", created_at="t0"))
    store.publish_version(
        PolicyVersionPublish(id="p-1-v1", policy_id="p-1", version_number=1, rules="{}", published_at="t0", published_by="a")
    )

    with pytest.raises(DuplicatePolicyVersion):
        store.publish_version(
            PolicyVersionPublish(id="p-1-v1-dup", policy_id="p-1", version_number=1, rules="{}", published_at="t1", published_by="a")
        )

    # The rejected attempt must not have changed current_version_id either.
    assert store.get_current_version("p-1")["id"] == "p-1-v1"
