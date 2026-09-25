"""SqliteAuditStoreAdapter -- implements the domain-facing `AuditStore`
port on top of the row-level SqliteAuditStore, translating a domain
AuditRecord into that store's DTO (P-01/P-06).
"""

from __future__ import annotations

import json

from sentinel.core.domain.audit.entities import AuditRecord
from sentinel.infrastructure.core.sqlite.audit_store import AuditRecordCreate, SqliteAuditStore
from sentinel.shared.logging import get_logger
from sentinel.shared.retry import retry_best_effort_write

_logger = get_logger("core", "SqliteAuditStoreAdapter")


class SqliteAuditStoreAdapter:
    def __init__(self, store: SqliteAuditStore) -> None:
        self._store = store

    def append(self, record: AuditRecord) -> None:
        retry_best_effort_write(
            lambda: self._store.append(
                AuditRecordCreate(
                    id=record.id,
                    actor=record.actor,
                    event_type=record.event_type,
                    origin=record.origin,
                    payload=json.dumps(record.payload),
                    created_at=record.created_at,
                    subject_analysis_id=record.subject_analysis_id,
                    correlation_id=record.correlation_id,
                )
            ),
            logger=_logger, event="audit_write", correlation_id=record.correlation_id, analysis_id=record.subject_analysis_id,
        )
