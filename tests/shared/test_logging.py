"""Proves structured JSON logging + secret redaction (Observability_and_Logging.md)."""

from __future__ import annotations

import json
import logging

from sentinel.shared.logging import configure_logging, get_logger


def test_log_line_is_json_with_required_fields(capsys) -> None:
    configure_logging(secret_values=())
    logger = get_logger(module_name="core", component="AnalysisOrchestrator")

    logger.info("t3_committed", "T3 committed: verdict=BLOCK", correlation_id="corr-1", analysis_id="an-1")

    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())

    assert payload["level"] == "INFO"
    assert payload["module"] == "core"
    assert payload["component"] == "AnalysisOrchestrator"
    assert payload["event"] == "t3_committed"
    assert payload["correlationId"] == "corr-1"
    assert payload["analysisId"] == "an-1"
    assert payload["scannerExecutionId"] is None
    assert payload["agentExecutionId"] is None
    assert payload["message"] == "T3 committed: verdict=BLOCK"


def test_secret_values_are_redacted_from_message_and_detail(capsys) -> None:
    configure_logging(secret_values=("super-secret-token",))
    logger = get_logger(module_name="core", component="GitHubAdapter")

    logger.error(
        "auth_failed",
        "call failed with token super-secret-token",
        detail={"token": "super-secret-token"},
    )

    captured = capsys.readouterr()
    assert "super-secret-token" not in captured.out
    assert "***REDACTED***" in captured.out


def test_log_level_filters_below_configured_level(capsys) -> None:
    configure_logging(secret_values=(), level=logging.WARNING)
    logger = get_logger(module_name="core", component="X")

    logger.info("noop", "should not appear")
    logger.warning("shown", "should appear")

    captured = capsys.readouterr()
    lines = [line for line in captured.out.strip().splitlines() if line]
    assert len(lines) == 1
    assert json.loads(lines[0])["event"] == "shown"
