"""Proves GitHubOAuthClient against a mocked HTTP transport (never real
GitHub, per Testing_Strategy.md's GitHub Integration Tests)."""

from __future__ import annotations

import httpx
import pytest

from sentinel.infrastructure.core.github.oauth_client import GitHubOAuthClient, GitHubOAuthError


def _client(handler) -> GitHubOAuthClient:
    return GitHubOAuthClient("client-id", "client-secret", transport=httpx.MockTransport(handler))


def test_build_authorize_url_includes_client_id_redirect_and_state() -> None:
    client = _client(lambda request: httpx.Response(200))

    url = client.build_authorize_url("https://sentinelai.example/auth/callback", "state-123")

    assert url.startswith("https://github.com/login/oauth/authorize?")
    assert "client_id=client-id" in url
    assert "state=state-123" in url
    assert "redirect_uri=" in url


def test_exchange_code_for_access_token_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/login/oauth/access_token"
        return httpx.Response(200, json={"access_token": "gho_test_token", "token_type": "bearer"})

    token = _client(handler).exchange_code_for_access_token("code-abc", "https://sentinelai.example/callback")

    assert token == "gho_test_token"


def test_exchange_code_raises_when_no_access_token_in_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": "bad_verification_code"})

    with pytest.raises(GitHubOAuthError):
        _client(handler).exchange_code_for_access_token("bad-code", "https://sentinelai.example/callback")


def test_exchange_code_raises_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    with pytest.raises(GitHubOAuthError):
        _client(handler).exchange_code_for_access_token("code-abc", "https://sentinelai.example/callback")


def test_fetch_authenticated_login_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer gho_test_token"
        return httpx.Response(200, json={"login": "dana-devsecops", "id": 123})

    login = _client(handler).fetch_authenticated_login("gho_test_token")

    assert login == "dana-devsecops"


def test_fetch_authenticated_login_raises_on_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad credentials"})

    with pytest.raises(GitHubOAuthError):
        _client(handler).fetch_authenticated_login("invalid-token")
