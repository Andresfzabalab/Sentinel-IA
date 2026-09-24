"""Proves the generic subprocess mechanics every scanner adapter relies on
(P-09): a forced timeout produces 'timed_out', a missing binary produces
'failed', and a normal run produces 'succeeded' with real stdout/exit
code -- never a hang, never an unhandled exception. Uses the current
Python interpreter as a cross-platform, always-available stand-in for a
real scanner binary, so this test doesn't depend on Semgrep/Bandit/Trivy/
Gitleaks/Checkov actually being installed on the machine running it.
"""

from __future__ import annotations

import sys

from sentinel.infrastructure.core.scanners.subprocess_runner import run_scanner_subprocess


def test_successful_run_captures_stdout_and_exit_code() -> None:
    outcome = run_scanner_subprocess(
        [sys.executable, "-c", "print('{\"ok\": true}')"], cwd="", timeout_seconds=5
    )

    assert outcome.status == "succeeded"
    assert outcome.exit_code == 0
    assert '"ok": true' in outcome.stdout


def test_a_nonzero_exit_code_is_still_reported_as_succeeded_process_execution() -> None:
    """Many scanners exit non-zero to mean 'findings reported' -- the
    subprocess runner itself must not conflate that with a crash; each
    adapter's own parsing decides success/failure of the scan."""
    outcome = run_scanner_subprocess([sys.executable, "-c", "import sys; sys.exit(1)"], cwd="", timeout_seconds=5)

    assert outcome.status == "succeeded"
    assert outcome.exit_code == 1


def test_a_forced_timeout_produces_timed_out_never_a_hang() -> None:
    outcome = run_scanner_subprocess(
        [sys.executable, "-c", "import time; time.sleep(5)"], cwd="", timeout_seconds=1
    )

    assert outcome.status == "timed_out"
    assert outcome.exit_code is None
    assert "timeout" in outcome.failure_note.lower()


def test_a_missing_binary_produces_failed_never_an_unhandled_exception() -> None:
    outcome = run_scanner_subprocess(["definitely-not-a-real-binary-xyz"], cwd="", timeout_seconds=5)

    assert outcome.status == "failed"
    assert outcome.exit_code is None
    assert outcome.failure_note is not None
