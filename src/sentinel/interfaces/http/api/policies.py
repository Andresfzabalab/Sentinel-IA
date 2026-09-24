"""POST /policies/{policyId}/versions -- API_Contract.md's UC-4/UC-9
(suppression is content within a version, not a separate endpoint)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from sentinel.interfaces.http.middleware.auth import require_devsecops_session

router = APIRouter()


class PublishPolicyVersionRequest(BaseModel):
    rules: dict


@router.post("/policies/{policy_id}/versions", status_code=201)
async def publish_policy_version(
    policy_id: str, body: PublishPolicyVersionRequest, request: Request,
    devsecops_login: str = Depends(require_devsecops_session),
) -> dict:
    deps = request.app.state.deps

    version = deps.policy_publishing_service.publish_version(policy_id, body.rules, actor=devsecops_login)

    return {
        "policyVersionId": version.id,
        "policyId": version.policy_id,
        "versionNumber": version.version_number,
        "rules": version.rules,
        "publishedAt": version.published_at,
        "publishedBy": version.published_by,
    }
