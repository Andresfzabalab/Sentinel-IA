"""NullWorkingDirectoryPort -- a test double that never touches the network
or filesystem. Used wherever a test needs the Orchestrator's real
GitHubRepositoryPort but must not trigger a real `git clone` (which would
otherwise dial out to github.com and could hang up to its timeout on a
network-isolated test runner).
"""

from __future__ import annotations

from sentinel.core.ports.working_directory_port import WorkingDirectoryPort


class NullWorkingDirectoryPort(WorkingDirectoryPort):
    def prepare(self, repository_external_id: str, head_commit_sha: str) -> str:
        return ""

    def cleanup(self, working_directory: str) -> None:
        pass
