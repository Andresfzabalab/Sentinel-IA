"""Proves GitHubRepositoryPort: change-kind mapping, failure translation
into RepositoryPortError, and verdict->Commit-Status-state mapping.
"""

from __future__ import annotations

import json

import httpx
import pytest

from sentinel.core.ports.repository_port import AnalysisResultSummary, RepositoryPortError
from sentinel.infrastructure.core.github.client import GitHubClient
from sentinel.infrastructure.core.github.repository_port_adapter import (
    GitHubRepositoryPort,
    split_external_identifier,
)


def _adapter(handler) -> GitHubRepositoryPort:
    transport = httpx.MockTransport(handler)
    client = GitHubClient(token="tok", transport=transport, sleep=lambda _seconds: None)
    return GitHubRepositoryPort(client)


def test_split_external_identifier() -> None:
    assert split_external_identifier("acme/widgets") == ("acme", "widgets")


def test_split_external_identifier_rejects_missing_slash() -> None:
    with pytest.raises(ValueError):
        split_external_identifier("acme-widgets")


def test_fetch_changed_files_maps_github_status_to_change_kind() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {"filename": "app.py", "status": "modified"},
                {"filename": "new.py", "status": "added"},
                {"filename": "old.py", "status": "removed"},
                {"filename": "renamed.py", "status": "renamed"},
            ],
        )

    files = _adapter(handler).fetch_changed_files("acme/widgets", 42)

    by_path = {f.path: f.change_kind for f in files}
    assert by_path["app.py"] == "modified"
    assert by_path["new.py"] == "added"
    assert by_path["old.py"] == "deleted"
    assert by_path["renamed.py"] == "modified"


def test_fetch_changed_files_raises_repository_port_error_on_persistent_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with pytest.raises(RepositoryPortError):
        _adapter(handler).fetch_changed_files("acme/widgets", 42)


def test_publish_result_maps_block_to_failure_state() -> None:
    posted = {}

    def handler(request: httpx.Request) -> httpx.Response:
        posted["body"] = json.loads(request.content)
        return httpx.Response(201)

    ok = _adapter(handler).publish_result(
        "acme/widgets", "sha1", AnalysisResultSummary(verdict="BLOCK", description="Blocked: 1 rule")
    )

    assert ok is True
    assert posted["body"]["state"] == "failure"
    assert posted["body"]["context"] == "sentinelai/security-analysis"


def test_publish_result_maps_error_verdict_to_error_state() -> None:
    posted = {}

    def handler(request: httpx.Request) -> httpx.Response:
        posted["body"] = json.loads(request.content)
        return httpx.Response(201)

    _adapter(handler).publish_result(
        "acme/widgets", "sha1", AnalysisResultSummary(verdict="ERROR", description="Could not retrieve PR context")
    )

    assert posted["body"]["state"] == "error"


def test_publish_result_returns_false_on_failure_never_raises() -> None:
    """A Notification failure must never propagate as an exception -- the
    verdict was already decided (Ubiquitous_Language.md)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    ok = _adapter(handler).publish_result("acme/widgets", "sha1", AnalysisResultSummary(verdict="PASS", description="ok"))

    assert ok is False
