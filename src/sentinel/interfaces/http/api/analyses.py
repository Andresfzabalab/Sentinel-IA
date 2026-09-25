"""POST /analyses, GET /analyses, GET /analyses/{id}, GET /analyses/{id}/report
-- API_Contract.md's UC-2 and UC-5.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel

from sentinel.ai_agent.application.report_generation_service import AnalysisNotCompleteError
from sentinel.core.application.analysis_orchestrator import AnalysisTrigger
from sentinel.core.domain.services.artifact_classification import ChangedFile
from sentinel.infrastructure.core.github.client import GitHubClientError
from sentinel.infrastructure.core.github.repository_port_adapter import split_external_identifier
from sentinel.interfaces.http.middleware.auth import require_devsecops_session
from sentinel.shared.contracts import CONTRACT_VERSION
from sentinel.shared.correlation import derive_mode_a_correlation_id, derive_mode_b_correlation_id
from sentinel.shared.errors import ApiError

router = APIRouter()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PrReference(BaseModel):
    prNumber: int


class ArtifactSetItem(BaseModel):
    path: str
    changeKind: str = "modified"


class TriggerAnalysisRequest(BaseModel):
    repositoryId: str
    prReference: PrReference | None = None
    artifactSet: list[ArtifactSetItem] | None = None
    idempotencyKey: str | None = None


@router.post("/analyses", status_code=202)
async def trigger_analysis(
    body: TriggerAnalysisRequest, request: Request, background_tasks: BackgroundTasks,
    devsecops_login: str = Depends(require_devsecops_session),
) -> dict:
    deps = request.app.state.deps
    repository = deps.repository_config_store.get_repository(body.repositoryId)

    if body.prReference is not None:
        trigger, existing_id = _build_mode_a_trigger(deps, body, repository)
    else:
        if not body.artifactSet:
            raise ApiError(400, "MISSING_ARTIFACT_SET", "Mode B requests must supply artifactSet")
        trigger, existing_id = _build_mode_b_trigger(deps, body, repository)

    background_tasks.add_task(deps.orchestrator.process, trigger)

    return {"correlationId": trigger.correlation_id, "analysisId": existing_id}


def _build_mode_a_trigger(deps, body: TriggerAnalysisRequest, repository_row):
    if repository_row is None:
        raise ApiError(404, "ANALYSIS_NOT_FOUND", f"repository {body.repositoryId!r} not found")

    owner, repo = split_external_identifier(repository_row["external_identifier"])
    try:
        pr_data = deps.github_client.get_pull_request(owner, repo, body.prReference.prNumber)
    except GitHubClientError as exc:
        raise ApiError(400, "COULD_NOT_RESOLVE_PR", str(exc))

    head_commit_sha = pr_data["head"]["sha"]
    correlation_id = derive_mode_a_correlation_id(body.repositoryId, body.prReference.prNumber, head_commit_sha)
    existing_id = deps.analysis_store.find_analysis_id_by_correlation_id(correlation_id)

    trigger = AnalysisTrigger(
        correlation_id=correlation_id,
        repository_id=body.repositoryId,
        trigger_mode="mode_a",
        pr_number=body.prReference.prNumber,
        base_branch=pr_data["base"]["ref"],
        head_branch=pr_data["head"]["ref"],
        author=pr_data["user"]["login"],
        head_commit_sha=head_commit_sha,
    )
    return trigger, existing_id


def _build_mode_b_trigger(deps, body: TriggerAnalysisRequest, repository_row):
    if repository_row is None:
        raise ApiError(404, "ANALYSIS_NOT_FOUND", f"repository {body.repositoryId!r} not found")

    correlation = derive_mode_b_correlation_id(body.repositoryId, body.idempotencyKey)
    existing_id = deps.analysis_store.find_analysis_id_by_correlation_id(correlation.correlation_id)

    trigger = AnalysisTrigger(
        correlation_id=correlation.correlation_id,
        repository_id=body.repositoryId,
        trigger_mode="mode_b",
        manual_trigger_key=correlation.manual_trigger_key,
        changed_files=tuple(ChangedFile(path=item.path, change_kind=item.changeKind) for item in body.artifactSet),
    )
    return trigger, existing_id


@router.get("/analyses")
async def resolve_by_correlation_id(
    request: Request, correlationId: str | None = None,
    devsecops_login: str = Depends(require_devsecops_session),
) -> dict:
    if not correlationId:
        raise ApiError(400, "MISSING_CORRELATION_ID", "correlationId query parameter is required")

    deps = request.app.state.deps
    analysis_id = deps.analysis_store.find_analysis_id_by_correlation_id(correlationId)
    status = None
    if analysis_id is not None:
        row = deps.analysis_store.get_analysis(analysis_id)
        status = row["status"] if row is not None else None

    return {"analysisId": analysis_id, "correlationId": correlationId, "status": status}


@router.get("/analyses/{analysis_id}")
async def get_analysis(
    analysis_id: str, request: Request, devsecops_login: str = Depends(require_devsecops_session),
) -> dict:
    deps = request.app.state.deps
    row = deps.analysis_store.get_analysis(analysis_id)
    if row is None:
        raise ApiError(404, "ANALYSIS_NOT_FOUND", f"analysis {analysis_id!r} not found")

    security_result = None
    if row["status"] == "completed":
        findings = deps.analysis_store.get_findings(analysis_id)
        security_result = {
            "contractVersion": CONTRACT_VERSION,
            "analysisId": analysis_id,
            "correlationId": row["correlation_id"],
            "findings": [{"contractVersion": CONTRACT_VERSION, **dict(f)} for f in findings],
            "securityScore": row["security_score"],
            "policyVersionId": row["policy_version_id"],
            "verdict": row["verdict"],
            "completedAt": row["completed_at"],
            "degradationFlags": {
                "anyScannerFailed": bool(row["degradation_any_scanner_failed"]),
                "aiAvailableAtCompletion": bool(row["degradation_ai_available_at_completion"]),
            },
        }

    return {
        "analysisId": analysis_id,
        "correlationId": row["correlation_id"],
        "status": row["status"],
        "failureReason": row["failure_reason"],
        "securityResult": security_result,
    }


@router.get("/analyses/{analysis_id}/report")
async def get_report(
    analysis_id: str, request: Request, audience: str = "devsecops",
    devsecops_login: str = Depends(require_devsecops_session),
) -> dict:
    if audience not in ("developer", "devsecops"):
        raise ApiError(400, "INVALID_AUDIENCE", "audience must be 'developer' or 'devsecops'")

    deps = request.app.state.deps
    row = deps.analysis_store.get_analysis(analysis_id)
    if row is None:
        raise ApiError(404, "ANALYSIS_NOT_FOUND", f"analysis {analysis_id!r} not found")

    try:
        report = deps.report_generation_service.generate(analysis_id, audience, generated_at=_utc_now_iso())
    except AnalysisNotCompleteError:
        raise ApiError(409, "ANALYSIS_NOT_COMPLETE", f"analysis {analysis_id!r} has no report yet")

    return {
        "contractVersion": CONTRACT_VERSION,
        "reportId": report.report_id,
        "analysisId": report.analysis_id,
        "audience": report.audience,
        "content": report.content,
        "aiSection": report.ai_section,
        "format": report.format,
        "generatedAt": report.generated_at,
    }
