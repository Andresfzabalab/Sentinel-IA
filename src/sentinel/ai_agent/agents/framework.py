"""Agent Execution Framework -- reusable infrastructure for any agent, not
built specifically for the Security Investigation Agent (AI_Agent_Architecture.md §4).

Provides: an Agent Registry (agent definitions -- role, allowed tools,
execution limits), and an execution context that enforces permissions and
execution limits on every tool call. Extensibility: a future agent is added
by registering a new AgentDefinition -- this module's mechanics never
change per agent (the same intent as P-07's provider independence, applied
to agents).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from sentinel.ai_agent.domain.entities import ExecutionLimits, ToolCallRecord


class ToolNotPermitted(RuntimeError):
    """A tool call outside the agent's declared permission profile."""


class ExecutionLimitExceeded(RuntimeError):
    """The agent tried to exceed its declared tool-call budget."""


@dataclass(frozen=True)
class AgentDefinition:
    agent_type: str
    allowed_tools: tuple[str, ...]
    execution_limits: ExecutionLimits


class AgentRegistry:
    """The set of agents SentinelAI can run. Security Investigation Agent
    is the first entry (AI_Agent_Architecture.md §4)."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentDefinition] = {}

    def register(self, definition: AgentDefinition) -> None:
        self._agents[definition.agent_type] = definition

    def get(self, agent_type: str) -> AgentDefinition:
        try:
            return self._agents[agent_type]
        except KeyError as exc:
            raise KeyError(f"no agent registered for agent_type={agent_type!r}") from exc


@dataclass
class AgentExecutionContext:
    """The bounded input + intermediate state for a single agent run. State
    does not persist or leak across Analyses -- a fresh context is built
    per execution and discarded afterward.
    """

    definition: AgentDefinition
    clock: Callable[[], str]
    tool_calls: list[ToolCallRecord] = field(default_factory=list)

    def call_tool(self, tool_name: str, tool_callable: Callable[..., Any], *args: Any) -> Any:
        """Every tool call is checked against the permission profile and
        the execution-limit budget *before* it runs -- guardrails are
        checked by the framework, not assumed from agent/LLM good behavior
        (AI_Agent_Architecture.md §7).
        """
        if tool_name not in self.definition.allowed_tools:
            raise ToolNotPermitted(f"{tool_name!r} is not in the permission profile for {self.definition.agent_type!r}")
        if len(self.tool_calls) >= self.definition.execution_limits.max_tool_calls:
            raise ExecutionLimitExceeded(
                f"max_tool_calls={self.definition.execution_limits.max_tool_calls} exceeded for {self.definition.agent_type!r}"
            )

        result = tool_callable(*args)

        summary = str(result)
        max_size = self.definition.execution_limits.max_output_size
        if len(summary) > max_size:
            summary = summary[:max_size] + "...(truncated)"

        self.tool_calls.append(ToolCallRecord(tool_name=tool_name, called_at=self.clock(), result_summary=summary))
        return result
