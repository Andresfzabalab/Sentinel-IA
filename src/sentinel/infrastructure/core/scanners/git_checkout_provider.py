"""GitCheckoutProvider -- the real WorkingDirectoryPort adapter (Phase 6).

Uses the `git` CLI (assumed present, as in any real CI/dev environment) to
shallow-clone the repository and check out the exact commit a webhook
delivery is about -- never a different, possibly-newer commit
(GitHub_Integration.md's rationale for using the webhook's own
head_commit_sha, applied here to the checkout too).
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Callable

from sentinel.core.ports.working_directory_port import WorkingDirectoryError, WorkingDirectoryPort


def default_https_clone_url(github_token: str, repository_external_id: str) -> str:
    return f"https://x-access-token:{github_token}@github.com/{repository_external_id}.git"


def _force_remove_readonly(func, path, exc_info) -> None:
    """`shutil.rmtree`'s onerror hook: git leaves files inside `.git/objects`
    read-only on Windows, which makes a plain rmtree fail silently under
    `ignore_errors=True` -- clear the read-only bit and retry once.
    """
    os.chmod(path, stat.S_IWRITE)
    func(path)


class GitCheckoutProvider(WorkingDirectoryPort):
    def __init__(
        self,
        github_token: str,
        *,
        clone_timeout_seconds: int = 60,
        clone_url_builder: Callable[[str, str], str] = default_https_clone_url,
    ) -> None:
        """`clone_url_builder` is a deliberate, narrow test seam -- letting a
        test point at a local bare repository (`file://...`) instead of
        real GitHub, without weakening the default production behavior.
        """
        self._github_token = github_token
        self._clone_timeout_seconds = clone_timeout_seconds
        self._clone_url_builder = clone_url_builder

    def prepare(self, repository_external_id: str, head_commit_sha: str) -> str:
        target_dir = tempfile.mkdtemp(prefix="sentinelai-checkout-")
        clone_url = self._clone_url_builder(self._github_token, repository_external_id)

        try:
            subprocess.run(
                ["git", "clone", "--quiet", "--no-checkout", clone_url, target_dir],
                timeout=self._clone_timeout_seconds, capture_output=True, text=True, check=True,
            )
            subprocess.run(
                ["git", "checkout", "--quiet", head_commit_sha],
                cwd=target_dir, timeout=self._clone_timeout_seconds, capture_output=True, text=True, check=True,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            shutil.rmtree(target_dir, onerror=_force_remove_readonly)
            raise WorkingDirectoryError(
                f"could not prepare checkout for {repository_external_id}@{head_commit_sha}: {exc}"
            ) from exc

        return target_dir

    def cleanup(self, working_directory: str) -> None:
        if not working_directory:
            return
        try:
            shutil.rmtree(working_directory, onerror=_force_remove_readonly)
        except OSError:
            # Best-effort: a leftover temp directory is a disk-hygiene
            # concern, never something that should propagate out of the
            # Orchestrator's finally block (P-09's spirit applied to
            # cleanup, not just scanning).
            pass
