"""GitHubOAuthClient -- the real adapter behind API_Contract.md's OAuth
Boundary Contract (DevSecOps authentication). Distinct from GitHubClient
(which uses the GITHUB_TOKEN PAT for PR retrieval/status/comments) --
this is a separate credential pair (GITHUB_OAUTH_CLIENT_ID/SECRET) and a
separate concern (Configuration_and_Secrets.md's Secrets table).
"""

from __future__ import annotations

import httpx

_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
_TOKEN_URL = "https://github.com/login/oauth/access_token"
_USER_API_URL = "https://api.github.com/user"


class GitHubOAuthError(Exception):
    """Raised when the OAuth code exchange or the identity lookup fails.
    Callers must treat this as a 401 -- never let it propagate as an
    unhandled exception (mirrors RepositoryPortError's role for the PAT flow).
    """


class GitHubOAuthClient:
    def __init__(self, client_id: str, client_secret: str, *, transport: httpx.BaseTransport | None = None) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._client = httpx.Client(transport=transport, timeout=10.0)

    def close(self) -> None:
        self._client.close()

    def build_authorize_url(self, redirect_uri: str, state: str) -> str:
        return str(
            httpx.URL(
                _AUTHORIZE_URL,
                params={"client_id": self._client_id, "redirect_uri": redirect_uri, "state": state, "scope": "read:user"},
            )
        )

    def exchange_code_for_access_token(self, code: str, redirect_uri: str) -> str:
        response = self._client.post(
            _TOKEN_URL,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        if response.status_code >= 400:
            raise GitHubOAuthError(f"token exchange failed with status {response.status_code}")

        body = response.json()
        access_token = body.get("access_token")
        if not access_token:
            raise GitHubOAuthError(f"no access_token in GitHub's response: {body}")
        return access_token

    def fetch_authenticated_login(self, access_token: str) -> str:
        response = self._client.get(
            _USER_API_URL,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
        )
        if response.status_code >= 400:
            raise GitHubOAuthError(f"failed to fetch authenticated user, status {response.status_code}")

        body = response.json()
        login = body.get("login")
        if not login:
            raise GitHubOAuthError(f"no login in GitHub's user response: {body}")
        return login
