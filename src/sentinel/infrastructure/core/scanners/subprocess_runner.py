"""Shared subprocess execution helper for every scanner adapter.

Implements P-09's core promise generically, once: a scanner subprocess
that crashes, times out, or isn't even installed must never let an
exception escape into the Orchestrator -- it always resolves to a
SubprocessOutcome with a 'failed' or 'timed_out' status, never raises.

Many scanners (Semgrep, Bandit, Checkov) use a non-zero exit code to mean
"findings were reported", not "the tool crashed" -- this helper only
reports whether the process itself ran to completion within its timeout;
each adapter's own JSON parsing decides whether the *content* represents a
successful scan.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class SubprocessOutcome:
    status: str  # 'succeeded' | 'failed' | 'timed_out'
    exit_code: int | None
    stdout: str
    stderr: str
    failure_note: str | None = None


def run_scanner_subprocess(command: list[str], *, cwd: str, timeout_seconds: int) -> SubprocessOutcome:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd or None,
            timeout=timeout_seconds,
            capture_output=True,
            text=True,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return SubprocessOutcome(
            status="timed_out", exit_code=None, stdout="", stderr="",
            failure_note=f"exceeded {timeout_seconds}s timeout",
        )
    except FileNotFoundError as exc:
        return SubprocessOutcome(
            status="failed", exit_code=None, stdout="", stderr="",
            failure_note=f"scanner binary not found: {exc}",
        )
    except OSError as exc:
        return SubprocessOutcome(
            status="failed", exit_code=None, stdout="", stderr="",
            failure_note=f"could not invoke scanner: {exc}",
        )

    return SubprocessOutcome(
        status="succeeded", exit_code=completed.returncode, stdout=completed.stdout, stderr=completed.stderr,
    )
