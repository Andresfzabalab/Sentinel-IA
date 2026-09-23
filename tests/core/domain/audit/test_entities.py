"""Proves AuditRecord is append-only (immutable after creation)."""

from __future__ import annotations

import dataclasses

import pytest

from sentinel.core.domain.audit.entities import AuditRecord


def test_audit_record_cannot_be_mutated_after_creation() -> None:
    record = AuditRecord(
        id="audit-1", actor="system", event_type="AnalysisCompleted", origin="sentinel-core",
        payload={"verdict": "BLOCK"}, created_at="t0", subject_analysis_id="an-1", correlation_id="corr-1",
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        record.payload = {"verdict": "PASS"}
