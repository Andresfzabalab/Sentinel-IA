"""FakeRepositoryPort -- the one reusable in-memory implementation of
RepositoryPort used across unit and application-layer tests
(Testing_Strategy.md: "not a mocking-framework mock reconstructed per test
file"). Scriptable: configure a canned changed-files list or a failure per
(repository_external_id, pr_number).
"""

from __future__ import annotations

from dataclasses import dataclass

from sentinel.core.ports.repository_port import (
    AnalysisResultSummary,
    ChangedFileRef,
    RepositoryPort,
    RepositoryPortError,
)


@dataclass
class PublishedResult:
    repository_external_id: str
    head_commit_sha: str
    result: AnalysisResultSummary


@dataclass
class PublishedComment:
    repository_external_id: str
    pr_number: int
    body: str


class FakeRepositoryPort(RepositoryPort):
    def __init__(self) -> None:
        self._changed_files: dict[tuple[str, int], tuple[ChangedFileRef, ...]] = {}
        self._failures: set[tuple[str, int]] = set()
        self.published_results: list[PublishedResult] = []
        self.published_comments: list[PublishedComment] = []
        self.publish_should_fail: bool = False
        self.publish_comment_should_fail: bool = False

    def script_changed_files(self, repository_external_id: str, pr_number: int, files: tuple[ChangedFileRef, ...]) -> None:
        self._changed_files[(repository_external_id, pr_number)] = files

    def script_failure(self, repository_external_id: str, pr_number: int) -> None:
        self._failures.add((repository_external_id, pr_number))

    def fetch_changed_files(self, repository_external_id: str, pr_number: int) -> tuple[ChangedFileRef, ...]:
        key = (repository_external_id, pr_number)
        if key in self._failures:
            raise RepositoryPortError(f"simulated retrieval failure for {key!r}")
        if key not in self._changed_files:
            raise RepositoryPortError(f"no scripted changed files for {key!r}")
        return self._changed_files[key]

    def publish_result(self, repository_external_id: str, head_commit_sha: str, result: AnalysisResultSummary) -> bool:
        self.published_results.append(PublishedResult(repository_external_id, head_commit_sha, result))
        return not self.publish_should_fail

    def publish_summary_comment(self, repository_external_id: str, pr_number: int, body: str) -> bool:
        self.published_comments.append(PublishedComment(repository_external_id, pr_number, body))
        return not self.publish_comment_should_fail
