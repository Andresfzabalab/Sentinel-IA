"""Proves OllamaProvider against a mocked HTTP transport -- success,
unreachable transport, HTTP error status, and malformed response all map
to the right outcome (AIProviderUnavailable for every failure mode, per
P-02/QA-04: no partial/garbage AdvisoryResponse is ever returned).
"""

from __future__ import annotations

import httpx
import pytest

from sentinel.ai_agent.ports.ai_provider_port import AdvisoryRequest, AIProviderUnavailable
from sentinel.infrastructure.ai_agent.providers.ollama_provider import OllamaProvider


def _request() -> AdvisoryRequest:
    return AdvisoryRequest(
        finding_category="sast", finding_rule_or_check_id="r1", finding_severity_level="high",
        finding_risk_level="high", artifact_path="app.py", knowledge_base_content=None,
    )


def test_generate_advisory_returns_the_response_text_on_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/generate"
        return httpx.Response(200, json={"response": "This finding means..."})

    provider = OllamaProvider("http://localhost:11434", "qwen2.5-coder", transport=httpx.MockTransport(handler))

    advisory = provider.generate_advisory(_request())

    assert advisory.explanation == "This finding means..."


def test_generate_advisory_raises_unavailable_on_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    provider = OllamaProvider("http://localhost:11434", "qwen2.5-coder", transport=httpx.MockTransport(handler))

    with pytest.raises(AIProviderUnavailable):
        provider.generate_advisory(_request())


def test_generate_advisory_raises_unavailable_on_http_error_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    provider = OllamaProvider("http://localhost:11434", "qwen2.5-coder", transport=httpx.MockTransport(handler))

    with pytest.raises(AIProviderUnavailable):
        provider.generate_advisory(_request())


def test_generate_advisory_raises_unavailable_on_malformed_response_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    provider = OllamaProvider("http://localhost:11434", "qwen2.5-coder", transport=httpx.MockTransport(handler))

    with pytest.raises(AIProviderUnavailable):
        provider.generate_advisory(_request())
