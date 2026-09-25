"""AgentExecution -- the Advisory, secondary Aggregate
(docs/02_Domain/Entities_Value_Objects.md, Aggregates_and_Boundaries.md).

Independent, non-blocking lifecycle: its absence or delay must never gate
or change a Security Result. Its one narrow write path back into Sentinel
Core is appending its own provenance to the Audit Record via
AuditRecorderPort -- it never touches Analysis, Finding, or Policy state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ExecutionStatus = Literal["running", "completed", "pending_unavailable"]


@dataclass(frozen=True)
class ToolCallRecord:
    tool_name: str
    called_at: str
    result_summary: str


@dataclass(frozen=True)
class ExecutionLimits:
    max_duration_seconds: int
    max_tool_calls: int
    max_output_size: int


@dataclass
class AgentExecution:
    id: str
    subject_analysis_id: str
    correlation_id: str
    agent_type: str
    execution_limits: ExecutionLimits
    started_at: str
    status: ExecutionStatus = "running"
    tool_calls_log: list[ToolCallRecord] = field(default_factory=list)
    knowledge_base_entries_used: list[tuple[str, int]] = field(default_factory=list)
    completed_at: str | None = None

    def complete(self, completed_at: str) -> None:
        self.status = "completed"
        self.completed_at = completed_at

    def mark_pending_unavailable(self) -> None:
        """The LLM/provider was unreachable. This must never block or delay
        the Analysis it references, which has already completed
        independently (AI_Agent_Architecture.md §8) -- resumable later into
        `completed` without touching the referenced Analysis.
        """
        self.status = "pending_unavailable"
