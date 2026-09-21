"""FastAPI application factory — the HTTP entry point of the composition root.

Phase 0 scope only: the startup gate (Configuration_and_Secrets.md),
structured logging, the generic error envelope, and a /health endpoint
proving the process starts and answers. The GitHub webhook (Phase 4) and
the DevSecOps API/CLI (Phase 8) are added in their own phases, per
docs/04_Data/Implementation_Strategy.md.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from sentinel.shared.config import Settings, load_settings
from sentinel.shared.errors import build_error_envelope
from sentinel.shared.logging import configure_logging, get_logger

_logger = get_logger(module_name="interfaces", component="app")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Builds the FastAPI app.

    If `settings` is not supplied, loads it from the environment via
    `load_settings()` — which raises `ConfigurationError` before any app
    object exists if a mandatory secret is missing. There is no
    partially-configured app to hand back (the Local Execution Gate).
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
