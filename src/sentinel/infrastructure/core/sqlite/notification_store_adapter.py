"""SqliteNotificationStoreAdapter -- implements the domain-facing
`NotificationStore` port on top of the row-level SqliteNotificationStore,
translating a domain Notification into that store's DTO (P-01/P-06).
"""

from __future__ import annotations

from sentinel.core.domain.notification.entities import Notification
from sentinel.infrastructure.core.sqlite.notification_store import (
    NotificationAttempt,
    SqliteNotificationStore,
)


class SqliteNotificationStoreAdapter:
    def __init__(self, store: SqliteNotificationStore) -> None:
        self._store = store

    def record_attempt(self, notification: Notification) -> None:
        self._store.record_attempt(
            NotificationAttempt(
                id=notification.id,
                analysis_id=notification.analysis_id,
                channel=notification.channel,
                status=notification.status,
                attempted_at=notification.attempted_at,
                content_snapshot=notification.content_snapshot,
            )
        )
