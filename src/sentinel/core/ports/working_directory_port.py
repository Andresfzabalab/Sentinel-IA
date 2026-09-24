"""WorkingDirectoryPort -- materializes a real, local checkout of a PR's
head commit so scanner adapters have actual files to read (Phase 5's
`ScannerPort.run(..., working_directory)` parameter, populated for real
starting Phase 6, per Implementation_Strategy.md).
"""

from __future__ import annotations

from typing import Protocol


class WorkingDirectoryError(Exception):
    """Raised when a working directory cannot be prepared. Caught by the
    Orchestrator, never allowed to propagate -- a checkout failure degrades
    to scanners running with no real files (which each adapter already
    handles honestly via P-09), it never blocks or fails the Analysis.
    """


class WorkingDirectoryPort(Protocol):
    def prepare(self, repository_external_id: str, head_commit_sha: str) -> str:
        """Returns a local directory path containing the checked-out commit."""
        ...

    def cleanup(self, working_directory: str) -> None:
        """Removes the directory prepare() returned. Always safe to call,
        including with an empty string (no-op).
        """
        ...
