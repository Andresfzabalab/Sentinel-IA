"""Structured JSON logging per docs/04_Data/Observability_and_Logging.md.

Every log line is one JSON object carrying: timestamp, level, module,
component, event, correlationId, analysisId, scannerExecutionId,
agentExecutionId, message, detail. Secret values (from
Configuration_and_Secrets.md's Secrets table) are redacted once here,
centrally — never re-implemented per call site, which is how redaction
rules silently get skipped in practice.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

_REDACTED = "***REDACTED***"


class SecretRedactionFilter(logging.Filter):
    """Scrubs known secret values out of every log record before it is emitted."""

    def __init__(self, secret_values: tuple[str, ...] = ()):
        super().__init__()
        self._secrets = tuple(s for s in secret_values if s)

    def filter(self, record: logging.LogRecord) -> bool:
        if self._secrets and isinstance(record.msg, str):
            for secret in self._secrets:
                if secret in record.msg:
                    record.msg = record.msg.replace(secret, _REDACTED)
        detail = getattr(record, "detail", None)
        if self._secrets and detail:
            record.detail = _redact_structure(detail, self._secrets)
        return True


def _redact_structure(value: Any, secrets: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        for secret in secrets:
            if secret in value:
                value = value.replace(secret, _REDACTED)
        return value
    if isinstance(value, dict):
        return {k: _redact_structure(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_structure(v, secrets) for v in value]
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "module": getattr(record, "module_name", record.module),
            "component": getattr(record, "component", record.name),
            "event": getattr(record, "event", None),
            "correlationId": getattr(record, "correlation_id", None),
            "analysisId": getattr(record, "analysis_id", None),
            "scannerExecutionId": getattr(record, "scanner_execution_id", None),
            "agentExecutionId": getattr(record, "agent_execution_id", None),
            "message": record.getMessage(),
            "detail": getattr(record, "detail", None) or {},
        }
        return json.dumps(payload, default=str)


def configure_logging(secret_values: tuple[str, ...] = (), level: int = logging.INFO) -> None:
    """Configures the root logger to emit one JSON object per line to stdout,
    with secret redaction applied to every record.
    """
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(SecretRedactionFilter(secret_values))
    root.addHandler(handler)


class SentinelLogger:
    """Thin wrapper enforcing the required structured fields on every call
    site, per module/component (Observability_and_Logging.md).

    `module_name` should be one of: core | ai_agent | intelligence | interfaces,
    mirroring Project_Structure.md's top-level layout.
    """

    def __init__(self, module_name: str, component: str):
        self._module_name = module_name
        self._component = component
        self._logger = logging.getLogger(f"{module_name}.{component}")

    def log(
        self,
        level: int,
        event: str,
        message: str,
        *,
        correlation_id: str | None = None,
        analysis_id: str | None = None,
        scanner_execution_id: str | None = None,
        agent_execution_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self._logger.log(
            level,
            message,
            extra={
                "module_name": self._module_name,
                "component": self._component,
                "event": event,
                "correlation_id": correlation_id,
                "analysis_id": analysis_id,
                "scanner_execution_id": scanner_execution_id,
                "agent_execution_id": agent_execution_id,
                "detail": detail,
            },
        )

    def debug(self, event: str, message: str, **kwargs: Any) -> None:
        self.log(logging.DEBUG, event, message, **kwargs)

    def info(self, event: str, message: str, **kwargs: Any) -> None:
        self.log(logging.INFO, event, message, **kwargs)

    def warning(self, event: str, message: str, **kwargs: Any) -> None:
        self.log(logging.WARNING, event, message, **kwargs)

    def error(self, event: str, message: str, **kwargs: Any) -> None:
        self.log(logging.ERROR, event, message, **kwargs)

    def critical(self, event: str, message: str, **kwargs: Any) -> None:
        self.log(logging.CRITICAL, event, message, **kwargs)


def get_logger(module_name: str, component: str) -> SentinelLogger:
    return SentinelLogger(module_name, component)
