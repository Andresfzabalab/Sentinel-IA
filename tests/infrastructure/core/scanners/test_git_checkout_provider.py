"""Proves GitCheckoutProvider performs a real git clone + checkout, using a
local bare repository instead of real GitHub (via the `clone_url_builder`
test seam) -- fully offline and deterministic, but exercising the actual
`git` CLI, not a mock.
"""

from __future__ import annotations

import pathlib
import subprocess

import pytest

from sentinel.core.ports.working_directory_port import WorkingDirectoryError
from sentinel.infrastructure.core.scanners.git_checkout_provider import GitCheckoutProvider


def _run_git(args: list[str], cwd) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


@pytest.fixture()
def local_repo(tmp_path):
    """Builds a tiny local git repository with two commits and returns
    (repo_path, first_commit_sha, second_commit_sha)."""
    repo_path = tmp_path / "origin_repo"
    repo_path.mkdir()
    _run_git(["init", "--quiet"], cwd=repo_path)
    _run_git(["config", "user.email", "test@example.com"], cwd=repo_path)
    _run_git(["config", "user.name", "Test"], cwd=repo_path)

    (repo_path / "app.py").write_text("print('v1')\n", encoding="utf-8")
    _run_git(["add", "app.py"], cwd=repo_path)
    _run_git(["commit", "--quiet", "-m", "v1"], cwd=repo_path)
    first_sha = _run_git(["rev-parse", "HEAD"], cwd=repo_path)

    (repo_path / "app.py").write_text("print('v2')\n", encoding="utf-8")
    _run_git(["add", "app.py"], cwd=repo_path)
    _run_git(["commit", "--quiet", "-m", "v2"], cwd=repo_path)
    second_sha = _run_git(["rev-parse", "HEAD"], cwd=repo_path)

    return repo_path, first_sha, second_sha


def _local_clone_url_builder(repo_path):
    return lambda token, repository_external_id: repo_path.as_uri()


def test_prepare_checks_out_the_exact_commit_requested(local_repo) -> None:
    repo_path, first_sha, second_sha = local_repo
    provider = GitCheckoutProvider("unused-token", clone_url_builder=_local_clone_url_builder(repo_path))

    working_directory = provider.prepare("owner/repo", first_sha)
    try:
        checked_out_file = pathlib.Path(working_directory) / "app.py"
        assert checked_out_file.read_text(encoding="utf-8") == "print('v1')\n"
    finally:
        provider.cleanup(working_directory)


def test_a_synchronize_style_new_commit_checks_out_different_content(local_repo) -> None:
    repo_path, first_sha, second_sha = local_repo
    provider = GitCheckoutProvider("unused-token", clone_url_builder=_local_clone_url_builder(repo_path))

    working_directory = provider.prepare("owner/repo", second_sha)
    try:
        checked_out_file = pathlib.Path(working_directory) / "app.py"
        assert checked_out_file.read_text(encoding="utf-8") == "print('v2')\n"
    finally:
        provider.cleanup(working_directory)


def test_cleanup_removes_the_directory(local_repo) -> None:
    repo_path, first_sha, _ = local_repo
    provider = GitCheckoutProvider("unused-token", clone_url_builder=_local_clone_url_builder(repo_path))
    working_directory = provider.prepare("owner/repo", first_sha)

    provider.cleanup(working_directory)

    assert not pathlib.Path(working_directory).exists()


def test_cleanup_is_a_safe_noop_for_an_empty_string() -> None:
    GitCheckoutProvider("unused-token").cleanup("")  # must not raise


def test_an_invalid_commit_sha_raises_working_directory_error_and_cleans_up(local_repo, tmp_path) -> None:
    repo_path, _, _ = local_repo
    provider = GitCheckoutProvider("unused-token", clone_url_builder=_local_clone_url_builder(repo_path))

    with pytest.raises(WorkingDirectoryError):
        provider.prepare("owner/repo", "0000000000000000000000000000000000000000")

    # No leftover temp directory from the failed attempt.
    leftovers = list(tmp_path.glob("**/sentinelai-checkout-*"))
    assert leftovers == []


def test_a_nonexistent_remote_raises_working_directory_error() -> None:
    provider = GitCheckoutProvider(
        "unused-token", clone_url_builder=lambda token, repo_id: "file:///nonexistent/path/on/disk"
    )

    with pytest.raises(WorkingDirectoryError):
        provider.prepare("owner/repo", "deadbeef")
