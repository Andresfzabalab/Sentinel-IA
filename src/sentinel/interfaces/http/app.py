"""FastAPI application factory — the HTTP entry point of the composition root.

Phase 0: the startup gate (Configuration_and_Secrets.md), structured
logging, the generic error envelope, and a /health endpoint. Phase 4 adds
the GitHub webhook router -- registered only when `dependencies` is
supplied, since the webhook needs the fully wired Orchestrator/stores that
only the composition root (interfaces/composition.py) can build. The
DevSecOps API/CLI (Phase 8) is added in its own phase, per
docs/04_Data/Implementation_Strategy.md.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from sentinel.shared.config import Settings, load_settings
from sentinel.shared.errors import build_error_envelope
from sentinel.shared.logging import configure_logging, get_logger

if TYPE_CHECKING:
    from sentinel.interfaces.composition import AppDependencies

_logger = get_logger(module_name="interfaces", component="app")


def create_app(settings: Settings | None = None, dependencies: "AppDependencies | None" = None) -> FastAPI:
    """Builds the FastAPI app.

    If `settings` is not supplied, loads it from the environment via
    `load_settings()` — which raises `ConfigurationError` before any app
    object exists if a mandatory secret is missing. There is no
    partially-configured app to hand back (the Local Execution Gate).

    `dependencies` (an `AppDependencies` bundle from composition.py) is
    optional so Phase 0/1-era tests can still build a route-less app with
    just `settings` -- passing it in registers the webhook router.
    """
    resolved_settings = settings or load_settings()
    configure_logging(secret_values=resolved_settings.secret_values())

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        _logger.info(
            "startup",
            "SentinelAI process started",
            detail={"database_path": resolved_settings.database_path},
        )
        yield

    app = FastAPI(title="SentinelAI", lifespan=lifespan)
    app.state.settings = resolved_settings

    if dependencies is not None:
        app.state.deps = dependencies
        from sentinel.interfaces.http.webhooks.github_webhook import router as github_webhook_router

        app.include_router(github_webhook_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        _logger.error("unhandled_exception", str(exc), detail={"path": request.url.path})
        return JSONResponse(
            status_code=500,
            content=build_error_envelope(code="INTERNAL_ERROR", message="An unexpected error occurred."),
        )

    return app
