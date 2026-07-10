"""Agent cognition package.

Public classes are resolved lazily so importing a narrow port such as
``physical_agent.agent.planner`` does not initialize chat, MCP, or application
adapters as a side effect.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from physical_agent.agent.chat_runtime import ChatRuntime
    from physical_agent.agent.llm_planner import LLMPlanner
    from physical_agent.agent.planner import Planner
    from physical_agent.agent.rule_based import RuleBasedPlanner
    from physical_agent.agent.runtime import AgentRuntime

__all__ = ["AgentRuntime", "ChatRuntime", "LLMPlanner", "Planner", "RuleBasedPlanner"]


def __getattr__(name: str) -> Any:
    if name == "AgentRuntime":
        from physical_agent.agent.runtime import AgentRuntime

        return AgentRuntime
    if name == "ChatRuntime":
        from physical_agent.agent.chat_runtime import ChatRuntime

        return ChatRuntime
    if name == "LLMPlanner":
        from physical_agent.agent.llm_planner import LLMPlanner

        return LLMPlanner
    if name == "Planner":
        from physical_agent.agent.planner import Planner

        return Planner
    if name == "RuleBasedPlanner":
        from physical_agent.agent.rule_based import RuleBasedPlanner

        return RuleBasedPlanner
    raise AttributeError(name)
