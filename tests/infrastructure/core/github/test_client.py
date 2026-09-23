"""Proves GitHubClient's retry/backoff, pagination, and rate-limit
handling against a mocked HTTP transport (Testing_Strategy.md's GitHub
Integration Tests: "mocked HTTP, not real GitHub, for the automated suite").
"""

from __future__ import annotations

import json
import time

import httpx
import pytest

from sentinel.infrastructure.core.github.client import GitHubClient, GitHubClientError


def _client(handler) -> GitHubClient:
    transport = httpx.MockTransport(handler)
    return GitHubClient(token="tok", transport=transport, sleep=lambda _seconds: None)


def test_get_pr_changed_files_single_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/acme/widgets/pulls/42/files"
        return httpx.Response(200, json=[{"filename": "app.py", "status": "modified"}])

    files = _client(handler).get_pr_changed_files("acme", "widgets", 42)

    assert files == [{"filename": "app.py", "status": "modified"}]


def test_get_pr_changed_files_follows_link_header_pagination() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if len(calls) == 1:
            return httpx.Response(
                200,
                json=[{"filename": "a.py", "status": "added"}],
                headers={
                    "Link": '<https://api.github.com/repos/acme/widgets/pulls/42/files?page=2>; rel="next"'
                },
            )
        return httpx.Response(200, json=[{"filename": "b.py", "status": "modified"}])

    files = _client(handler).get_pr_changed_files("acme", "widgets", 42)

    assert [f["filename"] for f in files] == ["a.py", "b.py"]
    assert len(calls) == 2


def test_retries_on_5xx_then_succeeds() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json=[])

    files = _client(handler).get_pr_changed_files("acme", "widgets", 42)

    assert files == []
    assert attempts["count"] == 3


def test_raises_after_retries_exhausted_on_persistent_5xx() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with pytest.raises(GitHubClientError):
        _client(handler).get_pr_changed_files("acme", "widgets", 42)


def test_does_not_retry_a_plain_4xx() -> None:
    """A 4xx (other than 429) indicates a request problem retrying won't
    fix (GitHub_Integration.md's Retries section)."""
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(404, json={"message": "Not Found"})

    with pytest.raises(GitHubClientError):
        _client(handler).get_pr_changed_files("acme", "widgets", 42)

    assert attempts["count"] == 1


def test_retries_on_429() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 2:
            return httpx.Response(429)
        return httpx.Response(200, json=[])

    _client(handler).get_pr_changed_files("acme", "widgets", 42)

    assert attempts["count"] == 2


def test_treats_rate_limited_403_as_transient_not_a_permissions_error() -> None:
    """Distinguished from a permissions 403 by the response body
    (GitHub_Integration.md's Rate Limits section)."""
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 2:
            return httpx.Response(403, json={"message": "API rate limit exceeded for user"})
        return httpx.Response(200, json=[])

    _client(handler).get_pr_changed_files("acme", "widgets", 42)

    assert attempts["count"] == 2


def test_a_genuine_permissions_403_is_not_retried() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(403, json={"message": "Resource not accessible by integration"})

    with pytest.raises(GitHubClientError):
        _client(handler).get_pr_changed_files("acme", "widgets", 42)

    assert attempts["count"] == 1


def test_tracks_rate_limit_headers_from_every_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=[], headers={"X-RateLimit-Remaining": "42", "X-RateLimit-Reset": "1999999999"}
        )

    client = _client(handler)
    client.get_pr_changed_files("acme", "widgets", 42)

    assert client.rate_limit.remaining == 42
    assert client.rate_limit.reset_epoch == 1999999999


def test_delays_non_urgent_calls_when_quota_nearly_exhausted() -> None:
    sleeps: list[float] = []
    call_count = {"n": 0}
    reset_at = int(time.time()) + 3

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        headers = {"X-RateLimit-Remaining": "2", "X-RateLimit-Reset": str(reset_at)}
        return httpx.Response(200, json=[], headers=headers)

    transport = httpx.MockTransport(handler)
    client = GitHubClient(token="tok", transport=transport, sleep=sleeps.append)

    client.get_pr_changed_files("acme", "widgets", 42)  # first call: learns remaining=2
    client.get_pr_changed_files("acme", "widgets", 42)  # second call: must wait for reset

    assert any(delay > 0 for delay in sleeps)


def test_post_commit_status_sends_the_documented_payload_shape() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        captured["path"] = request.url.path
        return httpx.Response(201)

    ok = _client(handler).post_commit_status(
        "acme", "widgets", "sha1", state="success", context="sentinelai/security-analysis", description="No blocking findings"
    )

    assert ok is True
    assert captured["path"] == "/repos/acme/widgets/statuses/sha1"
    assert captured["body"] == {
        "state": "success",
        "context": "sentinelai/security-analysis",
        "description": "No blocking findings",
    }


def test_post_issue_comment_sends_the_body() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(201)

    ok = _client(handler).post_issue_comment("acme", "widgets", 42, "Summary: no blocking findings")

    assert ok is True
    assert captured["body"] == {"body": "Summary: no blocking findings"}
