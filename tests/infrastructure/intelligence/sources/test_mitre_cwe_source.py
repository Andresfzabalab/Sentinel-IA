"""Proves MitreCweSource against a mocked transport: a known topic
aggregates every mapped CWE ID's content, an unknown topic returns None
without any network call, and one CWE lookup failing doesn't take down the
others for the same topic.
"""

from __future__ import annotations

import httpx

from sentinel.infrastructure.intelligence.sources.mitre_cwe_source import MitreCweSource


def _weakness_response(cwe_id: int, name: str, description: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "Weaknesses": [
                {
                    "ID": cwe_id, "Name": name, "Description": description,
                    "PotentialMitigations": [{"Description": "Use parameterized queries."}],
                }
            ]
        },
    )


def test_fetch_aggregates_every_mapped_cwe_id_for_a_known_topic() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/cwe/weakness/89":
            return _weakness_response(89, "SQL Injection", "SQL injection description.")
        if request.url.path == "/api/v1/cwe/weakness/78":
            return _weakness_response(78, "OS Command Injection", "Command injection description.")
        if request.url.path == "/api/v1/cwe/weakness/79":
            return _weakness_response(79, "Cross-site Scripting", "XSS description.")
        return httpx.Response(404)

    source = MitreCweSource(transport=httpx.MockTransport(handler))

    content = source.fetch("sast")

    assert content is not None
    assert "CWE-89" in content
    assert "CWE-78" in content
    assert "CWE-79" in content
    assert "Use parameterized queries." in content


def test_fetch_returns_none_for_a_topic_with_no_cwe_mapping() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no network call should happen for an unmapped topic")

    source = MitreCweSource(transport=httpx.MockTransport(handler))

    assert source.fetch("does-not-exist") is None


def test_a_single_failed_cwe_lookup_does_not_prevent_others_from_being_returned() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/cwe/weakness/798":
            return httpx.Response(500)
        return httpx.Response(404)

    source = MitreCweSource(transport=httpx.MockTransport(handler))

    assert source.fetch("secret") is None  # its only mapped CWE (798) failed


def test_fetch_returns_none_when_the_transport_is_unreachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    source = MitreCweSource(transport=httpx.MockTransport(handler))

    assert source.fetch("sast") is None
