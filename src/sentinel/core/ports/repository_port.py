"""RepositoryPort -- Infrastructure port to GitHub (docs/02_Domain/Ports_and_Interfaces.md).

The domain and Orchestrator depend only on this interface; GitHub-specific
types (webhook payloads, API models) stay inside the concrete adapter's
layer (P-08). The real adapter is built in Phase 4
(infrastructure/core/github/); Phase 3 exercised the Orchestrator against
a Fake implementation of this same interface.

Design note (fixed going into Phase 4): the only PR fact that genuinely
requires a GitHub API call is the changed-files list
(GitHub_Integration.md's "PR Retrieval and Changed Files"). Everything
else -- pr_number, base/head branch, author, and critically
head_commit_sha -- is already carried by the webhook payload itself and
must NEVER be re-derived from a separate API call (a later call could
observe a newer commit than the one this delivery is about, corrupting
Mode A's correlationId). So this port's surface is deliberately narrow:
`fetch_changed_files` is the only read operation, and the Orchestrator
supplies the webhook-known identity fields directly via AnalysisTrigger.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class RepositoryPortError(Exception):
    """Raised when changed files cannot be retrieved after retries are exhausted.

    Caught by the Orchestrator to trigger the T1-Failed path
    (Persistence_Strategy.md) -- never allowed to propagate as an
    unhandled exception.
    """


@dataclass(frozen=True)
class ChangedFileRef:
    path: str
    change_kind: str  # 'added' | 'modified' | 'deleted'


@dataclass(frozen=True)
class AnalysisResultSummary:
    """The minimal, mandatory content posted back to GitHub -- never waits
    on AI Enrichment or Agent Execution (AI_Agent_Architecture.md §8).
    """

    verdict: str  # 'PASS' | 'BLOCK' | 'ERROR'
    description: str


class RepositoryPort(Protocol):
    def fetch_changed_files(self, repository_external_id: str, pr_number: int) -> tuple[ChangedFileRef, ...]:
        """Raises RepositoryPortError if the list cannot be retrieved after
        the adapter's own retry policy is exhausted (GitHub_Integration.md).
        """
        ...

    def publish_result(self, repository_external_id: str, head_commit_sha: str, result: AnalysisResultSummary) -> bool:
        """Posts the mandatory status check (+ summary comment, for a real
        adapter). Returns whether delivery succeeded -- a failure here is a
        Notification concern, never a verdict concern (Ubiquitous_Language.md).
        """
        ...
