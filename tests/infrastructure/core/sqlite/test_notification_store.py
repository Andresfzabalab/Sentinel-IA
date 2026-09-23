"""Proves Notification delivery attempts are independent, per-attempt rows."""

from __future__ import annotations

from sentinel.infrastructure.core.sqlite.notification_store import (
    NotificationAttempt,
    SqliteNotificationStore,
)


def test_a_failed_attempt_and_its_retry_are_two_separate_rows(sqlite_conn, seeded_repository_id):
    store = SqliteNotificationStore(sqlite_conn)
    sqlite_conn.execute(
        "INSERT INTO analysis (id, correlation_id, trigger_mode, repository_id, policy_version_id, status, created_at) "
        "VALUES ('an-1', 'corr-1', 'mode_a', 'repo-1', 'policy-1-v1', 'completed', 't0')"
    )

    store.record_attempt(
        NotificationAttempt(id="notif-1", analysis_id="an-1", channel="github-status", status="failed", attempted_at="t1")
    )
    store.record_attempt(
        NotificationAttempt(id="notif-2", analysis_id="an-1", channel="github-status", status="delivered", attempted_at="t2")
    )

    attempts = store.get_by_analysis_id("an-1")
    assert [a["status"] for a in attempts] == ["failed", "delivered"]
