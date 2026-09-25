"""Proves CisaKevSource against a mocked transport: only the two relevant
topics (sca, container) trigger a fetch, entries are sorted most-recent-
first and capped, and any transport/HTTP failure degrades to None rather
than raising.
"""

from __future__ import annotations

import httpx

from sentinel.infrastructure.intelligence.sources.cisa_kev_source import CisaKevSource

_CATALOG_RESPONSE = {
    "vulnerabilities": [
        {"cveID": "CVE-2024-0001", "vendorProject": "Acme", "product": "Widget", "dateAdded": "2024-01-01"},
        {"cveID": "CVE-2024-0002", "vendorProject": "Acme", "product": "Gadget", "dateAdded": "2024-06-01"},
    ]
}


def test_fetch_returns_a_digest_for_a_relevant_topic() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_CATALOG_RESPONSE)

    source = CisaKevSource(transport=httpx.MockTransport(handler))

    content = source.fetch("sca")

    assert content is not None
    assert "CVE-2024-0002" in content
    # Most recently added listed before the older one.
    assert content.index("CVE-2024-0002") < content.index("CVE-2024-0001")


def test_fetch_returns_none_for_an_irrelevant_topic_without_any_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no network call should happen for an irrelevant topic")

    source = CisaKevSource(transport=httpx.MockTransport(handler))

    assert source.fetch("secret") is None


def test_fetch_returns_none_on_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    source = CisaKevSource(transport=httpx.MockTransport(handler))

    assert source.fetch("container") is None


def test_fetch_returns_none_on_http_error_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    source = CisaKevSource(transport=httpx.MockTransport(handler))

    assert source.fetch("sca") is None
