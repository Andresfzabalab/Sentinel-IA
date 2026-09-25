"""Shared prompt construction for every AIProviderPort adapter -- kept in
one place so every provider is asked the same question the same way, and
so no adapter is tempted to slip a verdict-shaped instruction into the
prompt (P-02 is enforced by the response TYPE, not the prompt wording, but
consistency here still matters for QA-06's "same behavior across providers").
"""

from __future__ import annotations

from sentinel.ai_agent.ports.ai_provider_port import AdvisoryRequest

_SYSTEM_PREAMBLE = (
    "You are a security advisory assistant. You explain security findings in "
    "plain language and suggest remediation. You never decide whether code "
    "should be merged or blocked -- that decision is made elsewhere, "
    "deterministically, and is not part of your task."
)


def build_prompt(request: AdvisoryRequest) -> str:
    knowledge_section = (
        f"Relevant remediation knowledge:\n{request.knowledge_base_content}"
        if request.knowledge_base_content
        else "No verified remediation knowledge is available for this finding category."
    )

    return (
        f"{_SYSTEM_PREAMBLE}\n\n"
        f"Finding category: {request.finding_category}\n"
        f"Rule/check id: {request.finding_rule_or_check_id}\n"
        f"Severity (scanner-assigned): {request.finding_severity_level}\n"
        f"Risk (context-adjusted): {request.finding_risk_level or 'not yet assessed'}\n"
        f"Artifact: {request.artifact_path}\n\n"
        f"{knowledge_section}\n\n"
        "Explain this finding in plain language, its likely consequence, and "
        "a prioritization hint. If remediation knowledge was provided above, "
        "suggest a remediation; otherwise do not invent one."
    )
