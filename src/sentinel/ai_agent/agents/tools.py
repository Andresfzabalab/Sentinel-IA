"""Tool Registry -- the internal, authorized tools an agent may call
(AI_Agent_Architecture.md §4). Every tool here is read-only by
construction: there is no write-capable tool registered for any agent in
the MVP (§7's guardrail table) -- not because callers are trusted not to
misuse one, but because no such tool exists to call.
"""

from __future__ import annotations

from sentinel.ai_agent.ports.security_knowledge_base_port import (
    KnowledgeBaseEntryView,
    SecurityKnowledgeBasePort,
)
from sentinel.ai_agent.ports.security_result_query_port import FindingView, SecurityResultView

READ_FINDINGS_TOOL = "ReadFindingsTool"
READ_RISK_BREAKDOWN_TOOL = "ReadRiskBreakdownTool"
READ_SECURITY_SCORE_TOOL = "ReadSecurityScoreTool"
READ_KNOWLEDGE_BASE_TOOL = "ReadKnowledgeBaseTool"

ALL_TOOL_NAMES = (READ_FINDINGS_TOOL, READ_RISK_BREAKDOWN_TOOL, READ_SECURITY_SCORE_TOOL, READ_KNOWLEDGE_BASE_TOOL)


def read_findings(security_result: SecurityResultView) -> tuple[FindingView, ...]:
    return security_result.findings


def read_risk_breakdown(security_result: SecurityResultView) -> tuple[tuple[str, str | None], ...]:
    return tuple((f.finding_id, f.risk_level) for f in security_result.findings)


def read_security_score(security_result: SecurityResultView) -> float:
    return security_result.security_score


class KnowledgeBaseTool:
    """The one tool that needs a collaborator (the cross-module port) rather
    than operating purely on the already-fetched SecurityResultView --
    still read-only, still bounded to a single query per call.
    """

    def __init__(self, knowledge_base_port: SecurityKnowledgeBasePort) -> None:
        self._port = knowledge_base_port

    def __call__(self, topic: str) -> KnowledgeBaseEntryView | None:
        return self._port.find_relevant(topic)
