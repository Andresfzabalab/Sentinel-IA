"""GitHubRepositoryPort -- the real RepositoryPort adapter (Phase 4).

Implements the two operations RepositoryPort actually needs: retrieving
the changed-files list (the one PR fact that genuinely requires an API
call) and publishing the mandatory result via the Commit Status API
(docs/03_API/GitHub_Integration.md). Everything else about a PR's identity
is already known from the webhook payload and flows through
AnalysisTrigger directly -- this adapter never re-derives it.
"""

from __future__ import annotations

from sentinel.core.ports.repository_port import (
    AnalysisResultSummary,
    ChangedFileRef,
    RepositoryPort,
    RepositoryPortError,
)
from sentinel.infrastructure.core.github.client import GitHubClient, GitHubClientError

_STATUS_CONTEXT = "sentinelai/security-analysis"
_STATE_BY_VERDICT = {"PASS": "success", "BLOCK": "failure", "ERROR": "error"}


def split_external_identifier(external_identifier: str) -> tuple[str, str]:
    owner, separator, repo = external_identifier.partition("/")
    if not separator:
        raise ValueError(f"repository external_identifier must be 'owner/repo', got {external_identifier!r}")
    return owner, repo


class GitHubRepositoryPort(RepositoryPort):
    def __init__(self, client: GitHubClient) -> None:
        self._client = client

    def fetch_changed_files(self, repository_external_id: str, pr_number: int) -> tuple[ChangedFileRef, ...]:
        owner, repo = split_external_identifier(repository_external_id)
        try:
            raw_files = self._client.get_pr_changed_files(owner, repo, pr_number)
        except GitHubClientError as exc:
            raise RepositoryPortError(str(exc)) from exc

        return tuple(
            ChangedFileRef(path=f["filename"], change_kind=_map_github_status(f.get("status", "modified")))
            for f in raw_files
        )

    def publish_result(self, repository_external_id: str, head_commit_sha: str, result: AnalysisResultSummary) -> bool:
        owner, repo = split_external_identifier(repository_external_id)
        state = _STATE_BY_VERDICT.get(result.verdict, "error")

        try:
            return self._client.post_commit_status(
                owner, repo, head_commit_sha,
                state=state, context=_STATUS_CONTEXT, description=result.description,
            )
        except GitHubClientError:
            return False

    def publish_summary_comment(self, repository_external_id: str, pr_number: int, body: str) -> bool:
        owner, repo = split_external_identifier(repository_external_id)
        try:
            return self._client.post_issue_comment(owner, repo, pr_number, body)
        except GitHubClientError:
            return False


def _map_github_status(github_status: str) -> str:
    """GitHub's PR-files API uses 'added'/'removed'/'modified'/'renamed' --
    SentinelAI's ChangedFileRef uses 'added'/'modified'/'deleted'
    (Entities_Value_Objects.md's Artifact VO). A rename is treated as a
    modification: the file still exists and still needs scanning.
    """
    if github_status == "removed":
        return "deleted"
    if github_status == "added":
        return "added"
    return "modified"
