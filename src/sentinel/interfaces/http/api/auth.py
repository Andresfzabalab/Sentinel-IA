"""GET /auth/login, GET /auth/callback, POST /auth/logout --
API_Contract.md's OAuth Boundary Contract.

On successful callback, SentinelAI issues its own short-lived session
token (never the raw GitHub token, which is held server-side only --
actually not held at all here, since it is used once to resolve the login
and then discarded). `POST /auth/logout` revokes SentinelAI's own session;
it does not revoke GitHub's OAuth grant (that stays under the DevSecOps
user's control via their GitHub account settings).
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from sentinel.infrastructure.core.github.oauth_client import GitHubOAuthError
from sentinel.infrastructure.core.sqlite.session_store import SessionCreate
from sentinel.interfaces.http.middleware.auth import SESSION_COOKIE_NAME
from sentinel.shared.errors import build_error_envelope

router = APIRouter()

_STATE_COOKIE_NAME = "sentinelai_oauth_state"
_SESSION_TTL = timedelta(hours=8)


@router.get("/auth/login")
async def login(request: Request) -> RedirectResponse:
    deps = request.app.state.deps
    state = secrets.token_urlsafe(24)
    redirect_uri = str(request.url_for("oauth_callback"))
    authorize_url = deps.oauth_client.build_authorize_url(redirect_uri, state)

    response = RedirectResponse(url=authorize_url, status_code=302)
    response.set_cookie(_STATE_COOKIE_NAME, state, httponly=True, max_age=600, samesite="lax")
    return response


@router.get("/auth/callback", name="oauth_callback")
async def callback(request: Request, code: str | None = None, state: str | None = None) -> JSONResponse:
    deps = request.app.state.deps
    expected_state = request.cookies.get(_STATE_COOKIE_NAME)

    if not code or not state or not expected_state or state != expected_state:
        return JSONResponse(
            status_code=401,
            content=build_error_envelope(code="INVALID_OAUTH_STATE", message="Invalid or missing OAuth state"),
        )

    try:
        redirect_uri = str(request.url_for("oauth_callback"))
        access_token = deps.oauth_client.exchange_code_for_access_token(code, redirect_uri)
        login_name = deps.oauth_client.fetch_authenticated_login(access_token)
    except GitHubOAuthError as exc:
        return JSONResponse(
            status_code=401, content=build_error_envelope(code="OAUTH_EXCHANGE_FAILED", message=str(exc))
        )

    session_token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    deps.session_store.create_session(
        SessionCreate(
            token=session_token, devsecops_login=login_name,
            created_at=now.isoformat(), expires_at=(now + _SESSION_TTL).isoformat(),
        )
    )

    response = JSONResponse(status_code=200, content={"status": "authenticated", "login": login_name})
    response.delete_cookie(_STATE_COOKIE_NAME)
    response.set_cookie(
        SESSION_COOKIE_NAME, session_token, httponly=True, max_age=int(_SESSION_TTL.total_seconds()), samesite="lax"
    )
    return response


@router.post("/auth/logout")
async def logout(request: Request) -> JSONResponse:
    deps = request.app.state.deps
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if session_token:
        deps.session_store.delete_session(session_token)

    response = JSONResponse(status_code=200, content={"status": "logged_out"})
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response
