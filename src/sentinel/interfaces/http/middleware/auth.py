"""OAuth session validation (API_Contract.md's OAuth Boundary Contract).

Every DevSecOps-facing route requires a valid session; an invalid or
absent one is 401, before any business logic runs -- the same
"reject before processing" posture already established for webhook
signature validation (GitHub_Integration.md).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Request

from sentinel.shared.errors import ApiError

SESSION_COOKIE_NAME = "sentinelai_session"


def require_devsecops_session(request: Request) -> str:
    """FastAPI dependency: returns the authenticated DevSecOps' GitHub
    login, or raises a 401 ApiError -- callers never see a request object
    with an unauthenticated session silently passed through.
    """
    deps = request.app.state.deps
    token = request.cookies.get(SESSION_COOKIE_NAME) or _extract_bearer_token(request)
    if not token:
        raise ApiError(401, "UNAUTHORIZED", "Missing session")

    session_row = deps.session_store.get_session(token)
    if session_row is None:
        raise ApiError(401, "UNAUTHORIZED", "Invalid session")

    if session_row["expires_at"] < datetime.now(timezone.utc).isoformat():
        raise ApiError(401, "UNAUTHORIZED", "Session expired")

    return session_row["devsecops_login"]


def _extract_bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization")
    if header and header.startswith("Bearer "):
        return header[len("Bearer ") :]
    return None
