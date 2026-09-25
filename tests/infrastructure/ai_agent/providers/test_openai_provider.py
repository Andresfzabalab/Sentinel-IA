"""Proves OpenAIProvider against a mocked HTTP transport: success with
structured JSON, unreachable transport, HTTP error status all map to
AIProviderUnavailable or a real AdvisoryResponse -- and a malformed JSON
*content* degrades to explanation-only rather than raising, since the
provider did respond (only unreachability/HTTP failure is unavailability).
"""

from __future__ import annotations

import json

import httpx
import pytest

from sentinel.ai_agent.ports.ai_provider_port import AdvisoryRequest, AIProviderUnavailable
from sentinel.infrastructure.ai_agent.providers.openai_provider import OpenAIProvider


def _request() -> AdvisoryRequest:
    return AdvisoryRequest(
        finding_category="sast", finding_rule_or_check_id="r1", finding_severity_level="high",
        finding_risk_level="high", artifact_path="app.py", knowledge_base_content=None,
    )


def _chat_completion_response(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_generate_advisory_parses_structured_json_on_success() -> None:
    body = json.dumps(
        {
            "explanation": "explanation text", "consequenceFraming": "framing",
            "prioritizationHint": "hint", "remediationSuggestion": "fix it",
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer sk-test"
        return _chat_completion_response(body)

    provider = OpenAIProvider("sk-test", transport=httpx.MockTransport(handler))

    advisory = provider.generate_advisory(_request())

    assert advisory.explanation == "explanation text"
    assert advisory.remediation_suggestion == "fix it"


def test_generate_advisory_degrades_to_explanation_only_on_malformed_json_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _chat_completion_response("not valid json at all")

    provider = OpenAIProvider("sk-test", transport=httpx.MockTransport(handler))

    advisory = provider.generate_advisory(_request())

    assert advisory.explanation == "not valid json at all"
    assert advisory.remediation_suggestion is None


def test_generate_advisory_raises_unavailable_on_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    provider = OpenAIProvider("sk-test", transport=httpx.MockTransport(handler))

    with pytest.raises(AIProviderUnavailable):
        provider.generate_advisory(_request())


def test_generate_advisory_raises_unavailable_on_http_error_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    provider = OpenAIProvider("sk-test", transport=httpx.MockTransport(handler))

    with pytest.raises(AIProviderUnavailable):
        provider.generate_advisory(_request())


def test_generate_advisory_raises_unavailable_on_unexpected_response_shape() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    provider = OpenAIProvider("sk-test", transport=httpx.MockTransport(handler))

    with pytest.raises(AIProviderUnavailable):
        provider.generate_advisory(_request())
