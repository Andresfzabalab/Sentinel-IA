"""Proves the app starts and answers /health (Implementation_Strategy.md's
Phase 0 proof: "the application starts, logs a structured startup event").
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from sentinel.interfaces.http.app import create_app
from sentinel.shared.config import Settings


def _fake_settings() -> Settings:
    return Settings(
        github_token="ghp_test",
        github_webhook_secret="whsec_test",
        github_oauth_client_id="client_id",
        github_oauth_client_secret="client_secret",
        database_path=":memory:",
    )


def test_health_endpoint_returns_ok() -> None:
    app = create_app(settings=_fake_settings())
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unhandled_exception_returns_error_envelope() -> None:
    app = create_app(settings=_fake_settings())

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("kaboom")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/boom")

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["correlationId"] is None
