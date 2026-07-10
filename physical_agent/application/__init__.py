"""Application use cases shared by CLI, HTTP, MCP, and agent facades."""

from physical_agent.application.plan_compiler import PlanCompiler, compile_agent_output
from physical_agent.application.output_projection import (
    current_agent_output,
    materialize_agent_output,
    project_chat_plan,
)
from physical_agent.application.proposals import ProposalResult, ProposalService

__all__ = [
    "PlanCompiler",
    "ProposalResult",
    "ProposalService",
    "compile_agent_output",
    "current_agent_output",
    "materialize_agent_output",
    "project_chat_plan",
]
