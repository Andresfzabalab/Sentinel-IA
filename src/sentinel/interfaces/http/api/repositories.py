"""POST /repositories/{repositoryId}/config -- API_Contract.md's UC-3."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from sentinel.core.application.repository_configuration_service import RepositoryConfigurationChange
from sentinel.core.domain.exceptions import EmptyEnabledScanners, RepositoryMissingPolicy
from sentinel.interfaces.http.middleware.auth import require_devsecops_session
from sentinel.shared.errors import ApiError

router = APIRouter()


class UpdateRepositoryConfigRequest(BaseModel):
    enabledScanners: list[str] | None = None
    assignedPolicyId: str | None = None
    aiProviderConfig: dict | None = None
    active: bool | None = None


@router.post("/repositories/{repository_id}/config")
async def update_repository_config(
    repository_id: str, body: UpdateRepositoryConfigRequest, request: Request,
    devsecops_login: str = Depends(require_devsecops_session),
) -> dict:
    deps = request.app.state.deps

    change = RepositoryConfigurationChange(
        enabled_scanners=tuple(body.enabledScanners) if body.enabledScanners is not None else None,
        assigned_policy_id=body.assignedPolicyId,
        ai_provider_config=body.aiProviderConfig,
        active=body.active,
    )

    try:
        repository = deps.repository_configuration_service.update(repository_id, change, actor=devsecops_login)
    except KeyError:
        raise ApiError(404, "REPOSITORY_NOT_FOUND", f"repository {repository_id!r} not found")
    except (RepositoryMissingPolicy, EmptyEnabledScanners) as exc:
        raise ApiError(400, "INVALID_CONFIGURATION", str(exc))

    return {
        "repositoryId": repository.id,
        "externalIdentifier": repository.external_identifier,
        "enabledScanners": list(repository.enabled_scanners),
        "assignedPolicyId": repository.assigned_policy_id,
        "aiProviderConfig": repository.ai_provider_config,
        "active": repository.active,
    }
