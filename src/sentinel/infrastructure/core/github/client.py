"""Thin GitHub REST API client (docs/03_API/GitHub_Integration.md).

Covers exactly what SentinelAI needs: the paginated changed-files list,
the Commit Status API, and the issue-comment endpoint (PR comments are
represented through the Issues API on GitHub). Implements the documented
retry/backoff policy and rate-limit tracking -- nothing more.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

_RETRY_DELAYS_SECONDS: tuple[float, ...] = (1.0, 2.0, 4.0)
_GITHUB_API_BASE = "https://api.github.com"
_RATE_LIMIT_SAFETY_MARGIN = 5


class GitHubClientError(Exception):
    """Raised when a GitHub API call fails after the retry policy is exhausted."""


@dataclass
class RateLimitState:
    remaining: int | None = None
    reset_epoch: int | None = None


class GitHubClient:
    """Synchronous by design -- consistent with the rest of Sentinel Core
    (the Orchestrator and every *Store adapter are sync); FastAPI's
    BackgroundTasks runs this in a threadpool, so no async/await is needed
    here (Project_Structure.md keeps the domain/application layers sync).
    """

    def __init__(
        self,
        token: str,
        *,
        base_url: str = _GITHUB_API_BASE,
        transport: httpx.BaseTransport | None = None,
        sleep: "callable[[float], None]" = time.sleep,
    ) -> None:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self._client = httpx.Client(base_url=base_url, headers=headers, transport=transport, timeout=10.0)
        self._sleep = sleep
        self.rate_limit = RateLimitState()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- Internal request machinery ---------------------------------------

    def _track_rate_limit(self, response: httpx.Response) -> None:
        remaining = response.headers.get("X-RateLimit-Remaining")
        reset = response.headers.get("X-RateLimit-Reset")
        if remaining is not None:
            self.rate_limit.remaining = int(remaining)
        if reset is not None:
            self.rate_limit.reset_epoch = int(reset)

    def _is_rate_limited_403(self, response: httpx.Response) -> bool:
        if response.status_code != 403:
            return False
        try:
            body = response.json()
        except ValueError:
            return False
        message = str(body.get("message", "")).lower()
        return "rate limit" in message

    def _wait_for_rate_limit_if_needed(self) -> None:
        """If remaining quota has dropped below the safety margin, delay
        until the documented reset time rather than spending the last of
        the quota (GitHub_Integration.md's Rate Limits section).
        """
        if self.rate_limit.remaining is None or self.rate_limit.reset_epoch is None:
            return
        if self.rate_limit.remaining > _RATE_LIMIT_SAFETY_MARGIN:
            return
        delay = max(0.0, self.rate_limit.reset_epoch - time.time())
        if delay > 0:
            self._sleep(delay)

    def _request_with_retry(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        self._wait_for_rate_limit_if_needed()

        last_response: httpx.Response | None = None
        last_error: Exception | None = None
        for delay in (0.0, *_RETRY_DELAYS_SECONDS):
            if delay:
                self._sleep(delay)
            try:
                response = self._client.request(method, url, **kwargs)
            except httpx.TransportError as exc:
                last_error = exc
                continue

            self._track_rate_limit(response)

            is_rate_limited = self._is_rate_limited_403(response)
            if response.status_code < 500 and response.status_code != 429 and not is_rate_limited:
                return response

            last_response = response

        if last_response is not None:
            return last_response
        raise GitHubClientError(f"{method} {url} failed after retries: {last_error}")

    # -- Public API ---------------------------------------------------------

    def get_pr_changed_files(self, owner: str, repo: str, pr_number: int) -> list[dict]:
        """Paginated per GitHub_Integration.md: follows the `Link` header
        (rel="next") until exhausted, up to 100 files per page.
        """
        files: list[dict] = []
        url: str | None = f"/repos/{owner}/{repo}/pulls/{pr_number}/files"
        params: dict[str, object] | None = {"per_page": 100}

        while url is not None:
            response = self._request_with_retry("GET", url, params=params)
            if response.status_code >= 400:
                raise GitHubClientError(
                    f"GET {url} returned {response.status_code}: {response.text[:200]}"
                )
            files.extend(response.json())
            url = response.links.get("next", {}).get("url")
            params = None  # the next URL already carries the full query string

        return files

    def post_commit_status(
        self, owner: str, repo: str, sha: str, *, state: str, context: str, description: str,
        target_url: str | None = None,
    ) -> bool:
        payload: dict[str, str] = {"state": state, "context": context, "description": description}
        if target_url:
            payload["target_url"] = target_url

        response = self._request_with_retry("POST", f"/repos/{owner}/{repo}/statuses/{sha}", json=payload)
        return response.status_code < 300

    def post_issue_comment(self, owner: str, repo: str, pr_number: int, body: str) -> bool:
        response = self._request_with_retry(
            "POST", f"/repos/{owner}/{repo}/issues/{pr_number}/comments", json={"body": body}
        )
        return response.status_code < 300
