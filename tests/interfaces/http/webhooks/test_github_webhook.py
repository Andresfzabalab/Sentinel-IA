"""Proves Phase 4's exit criterion (Implementation_Strategy.md): a webhook
delivery reaches the endpoint, is signature-verified, and is retrievable
end-to-end through to a Commit Status post. GitHub's REST API is mocked at
the HTTP-transport level (Testing_Strategy.md's GitHub Integration Tests),
never called for real in this automated suite; the real `git clone`
checkout (Phase 6) is stubbed out via NullWorkingDirectoryPort so this
suite never dials out to github.com or depends on network availability --
that real-checkout path has its own dedicated, fully offline tests in
tests/infrastructure/core/scanners/test_git_checkout_provider.py.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from sentinel.infrastructure.core.sqlite.policy_store import (
    PolicyCreate,
    PolicyVersionPublish,
    SqlitePolicyStore,
)
from sentinel.infrastructure.core.sqlite.notification_store import SqliteNotificationStore
from sentinel.infrastructure.core.sqlite.repository_config_store import (
    RepositoryCreate,
    SqliteRepositoryConfigStore,
)
from sentinel.infrastructure.schema import create_full_schema
from sentinel.interfaces.composition import build_dependencies
from sentinel.interfaces.http.app import create_app
from sentinel.shared.config import Settings
from tests.fakes.null_working_directory_port import NullWorkingDirectoryPort

_WEBHOOK_SECRET = "whsec_test"


def _settings(database_path: str) -> Settings:
    return Settings(
        github_token="ghp_test",
        github_webhook_secret=_WEBHOOK_SECRET,
        github_oauth_client_id="client_id",
        github_oauth_client_secret="client_secret",
        database_path=database_path,
    )


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(_WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _pull_request_payload(action: str = "opened", pr_number: int = 42, head_sha: str = "sha-1") -> dict:
    return {
        "action": action,
        "repository": {"full_name": "acme/widgets"},
        "pull_request": {
            "number": pr_number,
            "head": {"sha": head_sha, "ref": "feature"},
            "base": {"ref": "main"},
            "user": {"login": "dana"},
        },
    }


@pytest.fixture()
def github_calls():
    return {"statuses": [], "comments": [], "files_requested": 0}


@pytest.fixture()
def mock_github_transport(github_calls):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and "/pulls/" in request.url.path and request.url.path.endswith("/files"):
            github_calls["files_requested"] += 1
            return httpx.Response(200, json=[])
        if request.method == "POST" and "/statuses/" in request.url.path:
            github_calls["statuses"].append(json.loads(request.content))
            return httpx.Response(201)
        if request.method == "POST" and request.url.path.endswith("/comments"):
            github_calls["comments"].append(json.loads(request.content))
            return httpx.Response(201)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.fixture()
def client(tmp_path, mock_github_transport):
    db_path = tmp_path / "webhook_test.sqlite"
    settings = _settings(str(db_path))
    dependencies = build_dependencies(
        settings, github_transport=mock_github_transport, working_directory_port=NullWorkingDirectoryPort()
    )
    create_full_schema(dependencies.connection)

    policy_store = SqlitePolicyStore(dependencies.connection)
    policy_store.create_policy(PolicyCreate(id="policy-1", created_at="t0"))
    policy_store.publish_version(
        PolicyVersionPublish(
            id="policy-1-v1", policy_id="policy-1", version_number=1,
            rules=json.dumps({"blockOnSeverity": "critical"}), published_at="t0", published_by="devsecops-1",
        )
    )
    SqliteRepositoryConfigStore(dependencies.connection).create_repository(
        RepositoryCreate(
            id="repo-1", external_identifier="acme/widgets", enabled_scanners=json.dumps(["semgrep"]),
            assigned_policy_id="policy-1", created_at="t0", updated_at="t0",
        )
    )

    app = create_app(settings=settings, dependencies=dependencies)
    test_client = TestClient(app)
    test_client.dependencies = dependencies  # convenience handle for assertions
    yield test_client
    dependencies.connection.close()


def test_invalid_signature_is_rejected_before_any_processing(client) -> None:
    body = json.dumps(_pull_request_payload()).encode("utf-8")

    response = client.post(
        "/webhooks/github", content=body,
        headers={"X-Hub-Signature-256": "sha256=" + "0" * 64, "X-GitHub-Event": "pull_request"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_SIGNATURE"
    assert client.dependencies.analysis_store.find_analysis_id_by_correlation_id("anything") is None


def test_non_pull_request_event_is_ignored(client) -> None:
    body = b'{"zen": "Keep it logically awesome."}'

    response = client.post(
        "/webhooks/github", content=body,
        headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "ping"},
    )

    assert response.status_code == 202
    assert response.json()["status"] == "ignored"


def test_unhandled_action_is_ignored(client) -> None:
    body = json.dumps(_pull_request_payload(action="closed")).encode("utf-8")

    response = client.post(
        "/webhooks/github", content=body,
        headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "pull_request"},
    )

    assert response.status_code == 202
    assert response.json()["status"] == "ignored"


def test_unregistered_repository_is_ignored_without_crashing(client) -> None:
    payload = _pull_request_payload()
    payload["repository"]["full_name"] = "someone/unregistered"
    body = json.dumps(payload).encode("utf-8")

    response = client.post(
        "/webhooks/github", content=body,
        headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "pull_request"},
    )

    assert response.status_code == 202
    assert response.json()["status"] == "ignored"


def test_opened_pull_request_reaches_a_persisted_verdict_and_a_commit_status_post(client, github_calls) -> None:
    body = json.dumps(_pull_request_payload(action="opened")).encode("utf-8")

    response = client.post(
        "/webhooks/github", content=body,
        headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "pull_request"},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["correlationId"]
    assert payload["analysisId"] is None  # not yet resolved at acceptance time

    # TestClient runs BackgroundTasks synchronously before returning, so the
    # full pipeline (changed-files retrieval -> scanning -> T3 -> status
    # post) has already completed by this point.
    correlation_id = payload["correlationId"]
    analysis_id = client.dependencies.analysis_store.find_analysis_id_by_correlation_id(correlation_id)
    assert analysis_id is not None

    row = client.dependencies.analysis_store.get_analysis(analysis_id)
    assert row["status"] == "completed"
    assert row["verdict"] in ("PASS", "BLOCK")

    assert github_calls["files_requested"] == 1
    assert len(github_calls["statuses"]) == 1
    assert github_calls["statuses"][0]["context"] == "sentinelai/security-analysis"

    # Phase 10: the mandatory summary PR comment is posted alongside the
    # status check, and both delivery attempts are recorded as Notifications.
    assert len(github_calls["comments"]) == 1
    assert row["verdict"] in github_calls["comments"][0]["body"]

    notification_rows = SqliteNotificationStore(client.dependencies.connection).get_by_analysis_id(analysis_id)
    channels = {n["channel"]: n["status"] for n in notification_rows}
    assert channels == {"github-status": "delivered", "github-comment": "delivered"}


def test_redelivered_webhook_is_idempotent_end_to_end(client) -> None:
    body = json.dumps(_pull_request_payload(action="opened", head_sha="sha-dup")).encode("utf-8")
    headers = {"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "pull_request"}

    first = client.post("/webhooks/github", content=body, headers=headers)
    second = client.post("/webhooks/github", content=body, headers=headers)

    assert first.json()["correlationId"] == second.json()["correlationId"]
    correlation_id = first.json()["correlationId"]
    analysis_id = client.dependencies.analysis_store.find_analysis_id_by_correlation_id(correlation_id)

    # Second delivery's response should already resolve the existing analysisId.
    assert second.json()["analysisId"] == analysis_id
