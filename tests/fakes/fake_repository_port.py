"""FakeRepositoryPort -- the one reusable in-memory implementation of
RepositoryPort used across unit and application-layer tests
(Testing_Strategy.md: "not a mocking-framework mock reconstructed per test
file"). Scriptable: configure canned PR contexts or a failure per
(repository_external_id, pr_number).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sentinel.core.ports.repository_port import (
    AnalysisResultSummary,
    PullRequestContext,
    RepositoryPort,
    RepositoryPortError,
)


@dataclass
class PublishedResult:
    repository_external_id: str
    head_commit_sha: str
    result: AnalysisResultSummary


class FakeRepositoryPort(RepositoryPort):
    def __init__(self) -> None:
        self._contexts: dict[tuple[str, int], PullRequestContext] = {}
        self._failures: set[tuple[str, int]] = set()
        self.published_results: list[PublishedResult] = []
        self.publish_should_fail: bool = False

    def script_context(self, repository_external_id: str, pr_number: int, context: PullRequestContext) -> None:
        self._contexts[(repository_external_id, pr_number)] = context

    def script_failure(self, repository_external_id: str, pr_number: int) -> None:
        self._failures.add((repository_external_id, pr_number))

    def fetch_pr_context(self, repository_external_id: str, pr_number: int) -> PullRequestContext:
        key = (repository_external_id, pr_number)
        if key in self._failures:
            raise RepositoryPortError(f"simulated retrieval failure for {key!r}")
        if key not in self._contexts:
            raise RepositoryPortError(f"no scripted context for {key!r}")
        return self._contexts[key]

    def publish_result(self, repository_external_id: str, head_commit_sha: str, result: AnalysisResultSummary) -> bool:
        self.published_results.append(PublishedResult(repository_external_id, head_commit_sha, result))
        return not self.publish_should_fail
