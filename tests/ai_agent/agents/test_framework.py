"""Proves the Agent Execution Framework's guardrails
(AI_Agent_Architecture.md §7): a tool call outside the permission profile,
or beyond the execution-limit budget, is rejected by the framework itself
-- never left to the agent/LLM's good behavior.
"""

from __future__ import annotations

import pytest

from sentinel.ai_agent.agents.framework import (
    AgentDefinition,
    AgentExecutionContext,
    AgentRegistry,
    ExecutionLimitExceeded,
    ToolNotPermitted,
)
from sentinel.ai_agent.domain.entities import ExecutionLimits


def _definition(**overrides) -> AgentDefinition:
    defaults = dict(
        agent_type="test-agent",
        allowed_tools=("AllowedTool",),
        execution_limits=ExecutionLimits(max_duration_seconds=30, max_tool_calls=2, max_output_size=100),
    )
    defaults.update(overrides)
    return AgentDefinition(**defaults)


def test_registry_returns_a_registered_definition() -> None:
    registry = AgentRegistry()
    definition = _definition()
    registry.register(definition)

    assert registry.get("test-agent") is definition


def test_registry_raises_for_an_unknown_agent_type() -> None:
    registry = AgentRegistry()

    with pytest.raises(KeyError):
        registry.get("does-not-exist")


def test_call_tool_outside_the_permission_profile_is_rejected() -> None:
    context = AgentExecutionContext(definition=_definition(), clock=lambda: "t")

    with pytest.raises(ToolNotPermitted):
        context.call_tool("ForbiddenTool", lambda: "result")


def test_call_tool_within_the_permission_profile_succeeds_and_is_logged() -> None:
    context = AgentExecutionContext(definition=_definition(), clock=lambda: "t")

    result = context.call_tool("AllowedTool", lambda: "result")

    assert result == "result"
    assert len(context.tool_calls) == 1
    assert context.tool_calls[0].tool_name == "AllowedTool"


def test_exceeding_max_tool_calls_is_rejected() -> None:
    context = AgentExecutionContext(definition=_definition(), clock=lambda: "t")
    context.call_tool("AllowedTool", lambda: "one")
    context.call_tool("AllowedTool", lambda: "two")

    with pytest.raises(ExecutionLimitExceeded):
        context.call_tool("AllowedTool", lambda: "three")


def test_tool_output_beyond_max_output_size_is_truncated_in_the_log() -> None:
    definition = _definition(execution_limits=ExecutionLimits(max_duration_seconds=30, max_tool_calls=5, max_output_size=5))
    context = AgentExecutionContext(definition=definition, clock=lambda: "t")

    context.call_tool("AllowedTool", lambda: "0123456789")

    assert context.tool_calls[0].result_summary == "01234...(truncated)"
