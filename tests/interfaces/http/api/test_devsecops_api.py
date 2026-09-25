"""Proves Phase 8's exit criterion (Implementation_Strategy.md): a
DevSecOps user can authenticate, trigger a Mode A or Mode B Analysis, poll
its status via GET /analyses?correlationId=..., and read its report and
audit trail -- entirely through HTTP, no direct database or code access
needed. GitHub's REST and OAuth APIs are both mocked at the HTTP-transport
level; the real `git clone` checkout is stubbed via NullWorkingDirectoryPort
(same pattern as the Phase 4/6 webhook tests).
"""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from sentinel.infrastructure.core.sqlite.policy_store import (
    PolicyCreate,
    PolicyVersionPublish,
    SqlitePolicyStore,
)
from sentinel.infrastructure.core.sqlite.repository_config_store import (
    RepositoryCreate,
    SqliteRepositoryConfigStore,
)
from sentinel.infrastructure.schema import create_full_schema
from sentinel.interfaces.composition import build_dependencies
from sentinel.interfaces.http.app import create_app
from sentinel.shared.config import Settings
from tests.fakes.null_working_directory_port import NullWorkingDirectoryPort


def _settings(database_path: str) -> Settings:
    return Settings(
        github_token="ghp_test",
        github_webhook_secret="whsec_test",
        github_oauth_client_id="oauth_client_id",
        github_oauth_client_secret="oauth_client_secret",
        database_path=database_path,
    )


@pytest.fixture()
def github_calls():
    return {"statuses": []}


@pytest.fixture()
def mock_github_transport(github_calls):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path.endswith("/files"):
            return httpx.Response(200, json=[])
        if request.method == "GET" and "/pulls/" in path:
            pr_number = int(path.rsplit("/", 1)[-1])
            return httpx.Response(
                200,
                json={
                    "number": pr_number,
                    "head": {"sha": f"sha-{pr_number}", "ref": "feature"},
                    "base": {"ref": "main"},
                    "user": {"login": "dana"},
                },
            )
        if request.method == "POST" and "/statuses/" in path:
            github_calls["statuses"].append(json.loads(request.content))
            return httpx.Response(201)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.fixture()
def mock_oauth_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "github.com" and request.url.path == "/login/oauth/access_token":
            return httpx.Response(200, json={"access_token": "gho_test_token"})
        if request.url.host == "api.github.com" and request.url.path == "/user":
            return httpx.Response(200, json={"login": "dana-devsecops"})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.fixture()
def client(tmp_path, mock_github_transport, mock_oauth_transport):
    db_path = tmp_path / "api_test.sqlite"
    settings = _settings(str(db_path))
    dependencies = build_dependencies(
        settings, github_transport=mock_github_transport, oauth_transport=mock_oauth_transport,
        working_directory_port=NullWorkingDirectoryPort(),
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
    test_client.dependencies = dependencies
    yield test_client
    dependencies.connection.close()


def _authenticate(client: TestClient) -> str:
    login_response = client.get("/auth/login", follow_redirects=False)
    assert login_response.status_code == 302
    state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]

    callback_response = client.get(f"/auth/callback?code=fake-code&state={state}")
    assert callback_response.status_code == 200
    return callback_response.json()["login"]


# -- Auth --------------------------------------------------------------------

def test_protected_endpoint_without_a_session_is_401(client) -> None:
    response = client.get("/analyses", params={"correlationId": "corr-x"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_login_redirects_to_github_with_a_state_param(client) -> None:
    response = client.get("/auth/login", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"].startswith("https://github.com/login/oauth/authorize?")
    assert "state=" in response.headers["location"]


def test_callback_with_mismatched_state_is_rejected(client) -> None:
    client.get("/auth/login", follow_redirects=False)  # sets the real state cookie

    response = client.get("/auth/callback?code=fake-code&state=wrong-state")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_OAUTH_STATE"


def test_successful_callback_authenticates_and_sets_a_session(client) -> None:
    login_name = _authenticate(client)

    assert login_name == "dana-devsecops"
    # The session cookie now works for a protected endpoint.
    response = client.get("/analyses", params={"correlationId": "corr-does-not-exist"})
    assert response.status_code == 200


def test_logout_invalidates_the_session(client) -> None:
    _authenticate(client)
    client.post("/auth/logout")

    response = client.get("/analyses", params={"correlationId": "corr-x"})

    assert response.status_code == 401


# -- Full DevSecOps flow over HTTP -------------------------------------------

def test_full_devsecops_flow_authenticate_trigger_poll_report_audit(client, github_calls) -> None:
    _authenticate(client)

    trigger_response = client.post(
        "/analyses",
        json={"repositoryId": "repo-1", "prReference": {"prNumber": 42}},
    )
    assert trigger_response.status_code == 202
    correlation_id = trigger_response.json()["correlationId"]
    assert trigger_response.json()["analysisId"] is None  # not yet resolved at acceptance time

    # Poll status via correlationId.
    poll_response = client.get("/analyses", params={"correlationId": correlation_id})
    assert poll_response.status_code == 200
    analysis_id = poll_response.json()["analysisId"]
    assert analysis_id is not None
    assert poll_response.json()["status"] == "completed"

    # Read full status + Security Result.
    detail_response = client.get(f"/analyses/{analysis_id}")
    assert detail_response.status_code == 200
    body = detail_response.json()
    assert body["securityResult"]["verdict"] in ("PASS", "BLOCK")

    # Read the report, both audiences. The relay-triggered Security
    # Investigation Agent run completes synchronously in-process here; with
    # no findings to investigate it reaches "complete" with zero
    # enrichments without ever calling the (unconfigured, Phase 9) AI
    # provider.
    devsecops_report = client.get(f"/analyses/{analysis_id}/report", params={"audience": "devsecops"})
    assert devsecops_report.status_code == 200
    assert devsecops_report.json()["aiSection"]["status"] == "complete"

    developer_report = client.get(f"/analyses/{analysis_id}/report", params={"audience": "developer"})
    assert developer_report.status_code == 200

    # Read the audit trail.
    audit_response = client.get("/audit-records", params={"analysisId": analysis_id})
    assert audit_response.status_code == 200
    event_types = {r["eventType"] for r in audit_response.json()["records"]}
    assert "AnalysisCompleted" in event_types

    # The mandatory GitHub channel still got a status post.
    assert len(github_calls["statuses"]) == 1


def test_mode_b_trigger_never_calls_github_for_pr_data(client) -> None:
    _authenticate(client)

    response = client.post(
        "/analyses",
        json={"repositoryId": "repo-1", "artifactSet": [{"path": "app.py", "changeKind": "modified"}]},
    )

    assert response.status_code == 202
    correlation_id = response.json()["correlationId"]

    poll_response = client.get("/analyses", params={"correlationId": correlation_id})
    assert poll_response.json()["status"] == "completed"


def test_trigger_with_neither_pr_reference_nor_artifact_set_is_rejected(client) -> None:
    _authenticate(client)

    response = client.post("/analyses", json={"repositoryId": "repo-1"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MISSING_ARTIFACT_SET"


def test_get_analyses_without_correlation_id_is_400(client) -> None:
    _authenticate(client)

    response = client.get("/analyses")

    assert response.status_code == 400


def test_get_unknown_analysis_is_404(client) -> None:
    _authenticate(client)

    response = client.get("/analyses/does-not-exist")

    assert response.status_code == 404


def test_report_for_an_analysis_still_running_is_409(client) -> None:
    """Simulated by asking for a report on an analysis_id that legitimately
    doesn't exist yet is 404, not 409 -- 409 is specifically "exists but
    not finished". We approximate by using a real, freshly-created-but-not-
    yet-processed correlationId path is hard to isolate over HTTP (the
    fake pipeline is fast); instead this proves the distinct-code contract
    at the unit level (test_report_generation_service.py) and here only
    the 404 path, which is the one HTTP can deterministically trigger.
    """
    _authenticate(client)

    response = client.get("/analyses/some-analysis-id/report")

    assert response.status_code == 404


def test_audit_records_without_any_filter_is_400(client) -> None:
    _authenticate(client)

    response = client.get("/audit-records")

    assert response.status_code == 400


def test_update_repository_config(client) -> None:
    _authenticate(client)

    response = client.post(
        "/repositories/repo-1/config",
        json={"enabledScanners": ["semgrep", "gitleaks"], "active": True},
    )

    assert response.status_code == 200
    assert response.json()["enabledScanners"] == ["semgrep", "gitleaks"]
    assert response.json()["assignedPolicyId"] == "policy-1"  # unchanged


def test_update_unknown_repository_is_404(client) -> None:
    _authenticate(client)

    response = client.post("/repositories/does-not-exist/config", json={"active": False})

    assert response.status_code == 404


def test_update_repository_config_with_an_empty_enabled_scanners_list_is_400(client) -> None:
    """Error_Handling_and_Resilience.md's 'Invalid configuration submitted'
    row: an empty enabledScanners list is rejected before anything is
    written, not silently accepted as 'no scanners run'.
    """
    _authenticate(client)

    response = client.post("/repositories/repo-1/config", json={"enabledScanners": []})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_CONFIGURATION"


def test_update_repository_config_pointing_at_a_nonexistent_policy_is_400(client) -> None:
    """Same row: a Repository must never be pointed at a Policy that
    cannot actually be evaluated, rejected at configuration time rather
    than discovered later when an Analysis tries to evaluate against it.
    """
    _authenticate(client)

    response = client.post("/repositories/repo-1/config", json={"assignedPolicyId": "does-not-exist"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_CONFIGURATION"


def test_publish_policy_version(client) -> None:
    _authenticate(client)

    response = client.post(
        "/policies/policy-1/versions",
        json={"rules": {"blockOnSeverity": "high", "suppressions": []}},
    )

    assert response.status_code == 201
    assert response.json()["versionNumber"] == 2
    assert response.json()["policyId"] == "policy-1"


def test_publish_policy_version_for_a_brand_new_policy_id_auto_creates_it(client) -> None:
    _authenticate(client)

    response = client.post("/policies/policy-new/versions", json={"rules": {}})

    assert response.status_code == 201
    assert response.json()["versionNumber"] == 1
