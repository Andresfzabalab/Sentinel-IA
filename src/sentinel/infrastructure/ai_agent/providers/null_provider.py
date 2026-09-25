"""NullAIProvider -- the AIProviderPort used when no AI provider is
configured (`OLLAMA_BASE_URL`/`OPENAI_API_KEY` both absent,
Configuration_and_Secrets.md's optional-capability list). Always raises
AIProviderUnavailable so the Agent Execution Runner takes exactly the same
`pending_unavailable` path as a real outage (QA-04) -- there is no separate
"no provider configured" code path to keep in sync with the real one.
"""

from __future__ import annotations

from sentinel.ai_agent.ports.ai_provider_port import AdvisoryRequest, AdvisoryResponse, AIProviderUnavailable


class NullAIProvider:
    def generate_advisory(self, request: AdvisoryRequest) -> AdvisoryResponse:
        raise AIProviderUnavailable("no AI provider configured (OLLAMA_BASE_URL/OPENAI_API_KEY both unset)")
