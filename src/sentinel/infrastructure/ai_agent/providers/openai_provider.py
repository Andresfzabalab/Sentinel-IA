"""OpenAIProvider -- the real, API-based AIProviderPort adapter
(Objectives.md: "at least one local AI provider (Ollama) and one API
provider (OpenAI, Claude, or Gemini) behind the same AIProviderPort,
switchable via configuration only" -- QA-06).

Requests a structured JSON response so explanation/consequence/
prioritization/remediation can be split into separate fields; a parse
failure degrades to an explanation-only response rather than raising --
only a genuine unreachability/HTTP failure is AIProviderUnavailable.
"""

from __future__ import annotations

import json

import httpx

from sentinel.ai_agent.ports.ai_provider_port import AdvisoryRequest, AdvisoryResponse, AIProviderUnavailable
from sentinel.infrastructure.ai_agent.providers.prompt import build_prompt

_RESPONSE_FORMAT_INSTRUCTION = (
    '\n\nRespond as JSON with exactly these keys: "explanation", "consequenceFraming", '
    '"prioritizationHint", "remediationSuggestion" (the last three may be null).'
)


class OpenAIProvider:
    def __init__(
        self, api_key: str, model: str = "gpt-4o-mini", *, timeout_seconds: float = 30.0,
        base_url: str = "https://api.openai.com/v1", transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._model = model
        self._client = httpx.Client(
            base_url=base_url, transport=transport, timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )

    def close(self) -> None:
        self._client.close()

    def generate_advisory(self, request: AdvisoryRequest) -> AdvisoryResponse:
        prompt = build_prompt(request) + _RESPONSE_FORMAT_INSTRUCTION
        try:
            response = self._client.post(
                "/chat/completions",
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                },
            )
        except httpx.TransportError as exc:
            raise AIProviderUnavailable(f"OpenAI unreachable: {exc}") from exc

        if response.status_code >= 400:
            raise AIProviderUnavailable(f"OpenAI returned {response.status_code}: {response.text[:200]}")

        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError) as exc:
            raise AIProviderUnavailable(f"could not parse OpenAI response shape: {exc}") from exc

        return _parse_advisory_content(content)


def _parse_advisory_content(content: str) -> AdvisoryResponse:
    try:
        parsed = json.loads(content)
        return AdvisoryResponse(
            explanation=parsed["explanation"],
            consequence_framing=parsed.get("consequenceFraming"),
            prioritization_hint=parsed.get("prioritizationHint"),
            remediation_suggestion=parsed.get("remediationSuggestion"),
        )
    except (ValueError, KeyError):
        # Degrade to explanation-only rather than raising -- the provider
        # DID respond; a formatting mismatch is not an availability failure.
        return AdvisoryResponse(explanation=content)
