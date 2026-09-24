"""GET /audit-records -- API_Contract.md's UC-6."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from sentinel.interfaces.http.middleware.auth import require_devsecops_session
from sentinel.shared.errors import ApiError

router = APIRouter()


@router.get("/audit-records")
async def list_audit_records(
    request: Request,
    analysisId: str | None = None,
    correlationId: str | None = None,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
    devsecops_login: str = Depends(require_devsecops_session),
) -> dict:
    if not any((analysisId, correlationId, from_, to)):
        raise ApiError(400, "MISSING_FILTER", "At least one of analysisId, correlationId, from, to is required")

    deps = request.app.state.deps
    rows = deps.audit_store.find(analysis_id=analysisId, correlation_id=correlationId, from_ts=from_, to_ts=to)

    records = [
        {
            "id": row["id"],
            "subjectAnalysisId": row["subject_analysis_id"],
            "correlationId": row["correlation_id"],
            "actor": row["actor"],
            "eventType": row["event_type"],
            "origin": row["origin"],
            "payload": row["payload"],
            "createdAt": row["created_at"],
        }
        for row in rows
    ]
    return {"records": records}
