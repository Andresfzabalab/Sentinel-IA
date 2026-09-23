"""Storage-level invariant violations for Sentinel Core's tables.

These back up application-layer invariants with a second, SQL-level guard
(Persistence_Strategy.md's "belt and suspenders" pattern) -- they signal a
genuine bug (an attempt to re-decide an already-decided verdict, or to
complete a scanner execution that was never started or already completed),
never a normal, expected outcome.
"""

from __future__ import annotations


class ScannerExecutionNotRunning(RuntimeError):
    """Raised when T2 finds no matching scanner_execution row with status='running'."""


class VerdictAlreadySet(RuntimeError):
    """Raised when T3's `WHERE verdict IS NULL` guard affects zero rows."""
