"""RepositoryPort -- Infrastructure port to GitHub (docs/02_Domain/Ports_and_Interfaces.md).

The domain and Orchestrator depend only on this interface; GitHub-specific
types (webhook payloads, API models) stay inside the concrete adapter's
layer (P-08). The real adapter is built in Phase 4
(infrastructure/core/github/); Phase 3 exercises the Orchestrator against
a Fake implementation of this same interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class RepositoryPortError(Exception):
    """Raised when PR context cannot be retrieved after retries are exhausted.

    Caught by the Orchestrator to trigger the T1-Failed path
    (Persistence_Strategy.md) -- never allowed to propagate as an
    unhandled exception.
    """


@dataclass(frozen=True)
class ChangedFileRef:
    path: str
    change_kind: str  # 'added' | 'modified' | 'deleted'


@dataclass(frozen=True)
class PullRequestContext:
    """The read-only PR snapshot fetched for a Mode A trigger."""

    pr_number: int
    base_branch: str
    head_branch: str
    author: str
    head_commit_sha: str
    changed_files: tuple[ChangedFileRef, ...]


@dataclass(frozen=True)
class AnalysisResultSummary:
    """The minimal, mandatory content posted back to GitHub -- never waits
    on AI Enrichment or Agent Execution (AI_Agent_Architecture.md §8).
    """

    verdict: str  # 'PASS' | 'BLOCK' | 'ERROR'
    description: str


class RepositoryPort(Protocol):
    def fetch_pr_context(self, repository_external_id: str, pr_number: int) -> PullRequestContext:
        """Raises RepositoryPortError if context cannot be retrieved after
        the adapter's own retry policy is exhausted (GitHub_Integration.md).
        """
        ...

    def publish_result(self, repository_external_id: str, head_commit_sha: str, result: AnalysisResultSummary) -> bool:
        """Posts the mandatory status check (+ summary comment, for a real
        adapter). Returns whether delivery succeeded -- a failure here is a
        Notification concern, never a verdict concern (Ubiquitous_Language.md).
        """
        ...
