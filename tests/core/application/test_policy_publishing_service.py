"""Proves PolicyPublishingService (UC-4/UC-9, Phase 7): T-Policy as a
callable application-layer operation, auto-incrementing version numbers,
with every publish audited -- suppression is just content in `rules`."""

from __future__ import annotations

import pytest

from sentinel.core.application.policy_publishing_service import PolicyPublishingService
from sentinel.core.domain.exceptions import DuplicatePolicyVersion
from sentinel.infrastructure.core.sqlite.audit_store import SqliteAuditStore
from sentinel.infrastructure.core.sqlite.audit_store_adapter import SqliteAuditStoreAdapter
from sentinel.infrastructure.core.sqlite.policy_store import SqlitePolicyStore
from sentinel.infrastructure.core.sqlite.policy_store_adapter import SqlitePolicyStoreAdapter


@pytest.fixture()
def service(sqlite_conn):
    return PolicyPublishingService(
        SqlitePolicyStoreAdapter(SqlitePolicyStore(sqlite_conn)),
        SqliteAuditStoreAdapter(SqliteAuditStore(sqlite_conn)),
        clock=lambda: "2026-01-01T00:00:00Z",
    )


def test_create_policy_and_publish_first_version(service, sqlite_conn):
    service.create_policy("policy-1", actor="devsecops-1")
    version = service.publish_version("policy-1", {"blockOnSeverity": "critical"}, actor="devsecops-1")

    assert version.version_number == 1
    assert version.rules == {"blockOnSeverity": "critical"}

    rows = sqlite_conn.execute("SELECT * FROM audit_record WHERE event_type = 'PolicyVersionPublished'").fetchall()
    assert len(rows) == 1


def test_publishing_a_suppression_rule_is_just_a_new_version(service):
    """UC-9: no special mechanism -- publishing a suppression is the exact
    same operation as any other policy update."""
    service.create_policy("policy-1", actor="devsecops-1")
    service.publish_version("policy-1", {"blockOnSeverity": "critical"}, actor="devsecops-1")

    suppressed_version = service.publish_version(
        "policy-1",
        {
            "blockOnSeverity": "critical",
            "suppressions": [{"ruleOrCheckId": "known-false-positive", "artifactPath": "tests/"}],
        },
        actor="devsecops-1",
    )

    assert suppressed_version.version_number == 2
    assert suppressed_version.rules["suppressions"][0]["ruleOrCheckId"] == "known-false-positive"


def test_version_numbers_auto_increment_across_multiple_publishes(service):
    service.create_policy("policy-1", actor="devsecops-1")

    v1 = service.publish_version("policy-1", {}, actor="a")
    v2 = service.publish_version("policy-1", {}, actor="a")
    v3 = service.publish_version("policy-1", {}, actor="a")

    assert [v1.version_number, v2.version_number, v3.version_number] == [1, 2, 3]


def test_each_publish_is_audited_with_its_own_actor(service, sqlite_conn):
    service.create_policy("policy-1", actor="devsecops-1")
    service.publish_version("policy-1", {}, actor="devsecops-1")
    service.publish_version("policy-1", {}, actor="devsecops-2")

    rows = sqlite_conn.execute(
        "SELECT actor FROM audit_record WHERE event_type = 'PolicyVersionPublished' ORDER BY id"
    ).fetchall()
    assert [r["actor"] for r in rows] == ["devsecops-1", "devsecops-2"]
