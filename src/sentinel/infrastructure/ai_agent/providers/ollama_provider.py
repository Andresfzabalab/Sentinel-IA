"""OllamaProvider -- the real, local AIProviderPort adapter
(Technology_Strategy.md: chosen for running acceptably on CPU-only
hardware with quantized models -- Qwen/DeepSeek Coder).

Calls Ollama's local HTTP API (`localhost:11434` by default) -- never the
internet; per Module_Boundaries.md, the AI & Agent Module's only egress is
this single, pre-configured endpoint.
"""

from __future__ import annotations

import httpx

from sentinel.ai_agent.ports.ai_provider_port import AdvisoryRequest, AdvisoryResponse, AIProviderUnavailable
from sentinel.infrastructure.ai_agent.providers.prompt import build_prompt


class OllamaProvider:
    def __init__(
        self, base_url: str, model: str, *, timeout_seconds: float = 30.0, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._model = model
        self._client = httpx.Client(base_url=base_url, transport=transport, timeout=timeout_seconds)

    def close(self) -> None:
        self._client.close()

    def generate_advisory(self, request: AdvisoryRequest) -> AdvisoryResponse:
        prompt = build_prompt(request)
        try:
            response = self._client.post(
                "/api/generate", json={"model": self._model, "prompt": prompt, "stream": False}
            )
        except httpx.TransportError as exc:
            raise AIProviderUnavailable(f"Ollama unreachable: {exc}") from exc

        if response.status_code >= 400:
            raise AIProviderUnavailable(f"Ollama returned {response.status_code}: {response.text[:200]}")

        try:
            body = response.json()
            text = body["response"]
        except (ValueError, KeyError) as exc:
            raise AIProviderUnavailable(f"could not parse Ollama response: {exc}") from exc

        return AdvisoryResponse(explanation=text)
