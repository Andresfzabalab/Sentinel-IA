"""Proves SqlitePolicyStoreAdapter's Phase 7 publishing operations:
next_version_number's auto-increment, and duplicate detection translated
into the domain-level exception (never the infrastructure one)."""

from __future__ import annotations

import pytest

from sentinel.core.domain.exceptions import DuplicatePolicyVersion
from sentinel.infrastructure.core.sqlite.policy_store import SqlitePolicyStore
from sentinel.infrastructure.core.sqlite.policy_store_adapter import SqlitePolicyStoreAdapter


def test_next_version_number_starts_at_one(sqlite_conn):
    adapter = SqlitePolicyStoreAdapter(SqlitePolicyStore(sqlite_conn))
    adapter.create_policy("policy-1", "t0")

    assert adapter.next_version_number("policy-1") == 1


def test_next_version_number_increments_after_each_publish(sqlite_conn):
    adapter = SqlitePolicyStoreAdapter(SqlitePolicyStore(sqlite_conn))
    adapter.create_policy("policy-1", "t0")

    adapter.publish_version("policy-1", 1, {"blockOnSeverity": "high"}, "t0", "devsecops-1")
    assert adapter.next_version_number("policy-1") == 2

    adapter.publish_version("policy-1", 2, {"blockOnSeverity": "critical"}, "t1", "devsecops-1")
    assert adapter.next_version_number("policy-1") == 3


def test_publish_version_updates_current_and_preserves_history(sqlite_conn):
    adapter = SqlitePolicyStoreAdapter(SqlitePolicyStore(sqlite_conn))
    adapter.create_policy("policy-1", "t0")

    v1 = adapter.publish_version("policy-1", 1, {"blockOnSeverity": "high"}, "t0", "devsecops-1")
    v2 = adapter.publish_version("policy-1", 2, {"blockOnSeverity": "critical"}, "t1", "devsecops-1")

    assert adapter.get_current_policy_version("policy-1").id == v2.id
    assert adapter.get_version(v1.id).rules == {"blockOnSeverity": "high"}  # untouched


def test_publishing_a_duplicate_version_number_raises_the_domain_exception_not_the_infra_one(sqlite_conn):
    adapter = SqlitePolicyStoreAdapter(SqlitePolicyStore(sqlite_conn))
    adapter.create_policy("policy-1", "t0")
    adapter.publish_version("policy-1", 1, {}, "t0", "devsecops-1")

    with pytest.raises(DuplicatePolicyVersion):
        adapter.publish_version("policy-1", 1, {"different": "rules"}, "t1", "devsecops-1")
