"""Shared "run subprocess, parse JSON, map to NormalizedFindingData" flow
used by every scanner adapter -- factored out once so P-05's translation
boundary (native format never leaks past the adapter) and P-09's
failure-isolation promise are implemented consistently, not re-derived per
tool.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from sentinel.core.ports.scanner_port import NormalizedFindingData, ScannerRunResult
from sentinel.infrastructure.core.scanners.subprocess_runner import run_scanner_subprocess
from sentinel.shared.logging import get_logger

_logger = get_logger("core", "ScannerAdapter")


def run_and_parse_json_scanner(
    command: list[str],
    *,
    cwd: str,
    timeout_seconds: int,
    parse: Callable[[Any], tuple[NormalizedFindingData, ...]],
    empty_output_value: Any = None,
) -> ScannerRunResult:
    """`empty_output_value` is what to parse when stdout is blank -- some
    tools (e.g. Gitleaks with zero findings) print nothing rather than an
    empty JSON structure.
    """
    outcome = run_scanner_subprocess(command, cwd=cwd, timeout_seconds=timeout_seconds)
    if outcome.status != "succeeded":
        return ScannerRunResult(status=outcome.status, exit_code=outcome.exit_code, failure_note=outcome.failure_note)

    stdout = outcome.stdout.strip()
    if not stdout:
        raw: Any = empty_output_value
    else:
        try:
            raw = json.loads(stdout)
        except json.JSONDecodeError as exc:
            _logger.error(
                "scanner_adapter_internal_exception", f"could not parse scanner output as JSON: {exc}",
                detail={"command": command[0] if command else None},
            )
            return ScannerRunResult(
                status="failed", exit_code=outcome.exit_code,
                failure_note=f"could not parse output as JSON: {exc}",
            )

    try:
        findings = parse(raw)
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        _logger.error(
            "scanner_adapter_internal_exception", f"could not interpret scanner output shape: {exc}",
            detail={"command": command[0] if command else None},
        )
        return ScannerRunResult(
            status="failed", exit_code=outcome.exit_code,
            failure_note=f"could not interpret scanner output shape: {exc}",
        )

    return ScannerRunResult(status="succeeded", exit_code=outcome.exit_code, findings=findings)
