"""API error envelope per docs/03_API/API_Contract.md's Error Model.

Every error response — from any endpoint, in any module — shares this one
shape. correlationId is echoed back whenever the request carried or
produced one; it is never fabricated when absent.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    correlationId: str | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


def build_error_envelope(code: str, message: str, correlation_id: str | None = None) -> dict[str, Any]:
    """Builds the error envelope dict as specified in API_Contract.md's Error Model."""
    return ErrorEnvelope(error=ErrorDetail(code=code, message=message, correlationId=correlation_id)).model_dump()


class ApiError(HTTPException):
    """Raised by any DevSecOps-facing route/dependency to produce
    API_Contract.md's exact error envelope shape -- never FastAPI's default
    `{"detail": ...}` body. Caught by app.py's dedicated exception handler.
    """

    def __init__(self, status_code: int, code: str, message: str, correlation_id: str | None = None) -> None:
        super().__init__(status_code=status_code, detail={"code": code, "message": message, "correlationId": correlation_id})
