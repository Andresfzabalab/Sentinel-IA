"""POST /webhooks/github -- the product's primary entry point (UC-1).

Implements docs/03_API/GitHub_Integration.md and API_Contract.md's webhook
endpoint: signature verification first (before any parsing), filtered to
`pull_request` events with action `opened`/`synchronize`, deriving
correlationId (Mode A) and responding quickly while the actual Analysis
(PR retrieval, scanning, T1-T3) runs in the background -- GitHub's webhook
delivery timeout must never be at risk of being exceeded by the full
pipeline (GitHub_Integration.md's Failure Handling).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from sentinel.core.application.analysis_orchestrator import AnalysisTrigger
from sentinel.infrastructure.core.github.signature import verify_github_signature
from sentinel.shared.correlation import derive_mode_a_correlation_id
from sentinel.shared.errors import build_error_envelope
from sentinel.shared.logging import get_logger

router = APIRouter()
_logger = get_logger(module_name="core", component="GitHubWebhook")

_HANDLED_ACTIONS = {"opened", "synchronize"}


@router.post("/webhooks/github")
async def receive_github_webhook(request: Request, background_tasks: BackgroundTasks) -> JSONResponse:
    body = await request.body()
    signature_header = request.headers.get("X-Hub-Signature-256")
    deps = request.app.state.deps

    if not verify_github_signature(deps.settings.github_webhook_secret, body, signature_header):
        # Rejected before any parsing or correlationId derivation --
        # System_Boundaries.md's "untrusted input, must be verified" rule.
        return JSONResponse(
            status_code=401,
            content=build_error_envelope(code="INVALID_SIGNATURE", message="Invalid webhook signature"),
        )

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=400,
            content=build_error_envelope(code="MALFORMED_PAYLOAD", message="Could not parse webhook payload"),
        )

    event_type = request.headers.get("X-GitHub-Event")
    if event_type != "pull_request":
        # Acknowledged, not rejected -- avoids GitHub retrying a webhook
        # SentinelAI has no use for (GitHub_Integration.md's Webhook Events table).
        return JSONResponse(status_code=202, content={"status": "ignored", "reason": "unsupported event type"})

    action = payload.get("action")
    if action not in _HANDLED_ACTIONS:
        return JSONResponse(status_code=202, content={"status": "ignored", "reason": f"unsupported action {action!r}"})

    pr = payload["pull_request"]
    repository_external_id = payload["repository"]["full_name"]
    pr_number = pr["number"]
    head_commit_sha = pr["head"]["sha"]  # the webhook's own value -- never re-derived via API

    repository_row = deps.repository_config_store.get_repository_by_external_identifier(repository_external_id)
    if repository_row is None or not repository_row["active"]:
        _logger.warning(
            "repository_not_registered",
            f"Webhook received for unregistered/inactive repository {repository_external_id!r}",
        )
        return JSONResponse(status_code=202, content={"status": "ignored", "reason": "repository not registered or inactive"})

    repository_id = repository_row["id"]
    correlation_id = derive_mode_a_correlation_id(repository_id, pr_number, head_commit_sha)

    existing_analysis_id = deps.analysis_store.find_analysis_id_by_correlation_id(correlation_id)

    trigger = AnalysisTrigger(
        correlation_id=correlation_id,
        repository_id=repository_id,
        trigger_mode="mode_a",
        pr_number=pr_number,
        base_branch=pr["base"]["ref"],
        head_branch=pr["head"]["ref"],
        author=pr["user"]["login"],
        head_commit_sha=head_commit_sha,
    )

    # The idempotency check above is synchronous and fast; the rest of the
    # pipeline (PR retrieval, scanning, T1-T3) runs after this response is
    # sent, per GitHub_Integration.md's Failure Handling section.
    background_tasks.add_task(deps.orchestrator.process, trigger)

    return JSONResponse(status_code=202, content={"correlationId": correlation_id, "analysisId": existing_analysis_id})
