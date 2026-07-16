from __future__ import annotations

from pathlib import Path
from typing import Any

from physical_agent.application.plan_compiler import task_graph_steps
from physical_agent.application.output_projection import project_chat_plan
from physical_agent.application.proposals import ProposalService
from physical_agent.agent.planner_factory import create_planner
from physical_agent.config import DEFAULT_CONFIG_NAME, load_config
from physical_agent.protocol.actions import SAFETY_INTENT_JSON_SCHEMA
from physical_agent.protocol.expectations import EXPECTED_JSON_SCHEMA
from physical_agent.protocol.schemas import Action, ChatPlan
from physical_agent.state import StateStore, open_state_store


class PhysicalAgentMCP:
    """Lightweight MCP-shaped facade over the configured workspace state store.

    The v1 package keeps this dependency-free so MCP support does not become
    part of the critical watch/agent loop. A future adapter can expose these
    methods through a concrete MCP server library.
    """

    def __init__(self, config_path: str | Path = DEFAULT_CONFIG_NAME):
        self.config_path = Path(config_path).resolve()

    async def submit_task(self, task: str) -> dict[str, Any]:
        config = load_config(self.config_path)
        workspace = open_state_store(config, base_dir=self.config_path.parent)
        if not workspace.exists():
            workspace.initialize()
        proposal = ProposalService(
            workspace,
            planner_factory=lambda: create_planner(
                config,
                base_dir=self.config_path.parent,
            ),
        ).submit_task(
            task,
            proposed_by="mcp",
        )
        agent_output = proposal.agent_output
        actions = agent_output.actions
        self._write_agent_plan(workspace, task, agent_output)
        if not proposal.ok:
            workspace.append_log(proposal.message, actor="mcp")
            return {
                "ok": False,
                "message": proposal.message,
                "agent_output": agent_output.model_dump(
                    mode="json", by_alias=True
                ),
                "refusal_reason": proposal.refusal_reason,
                "proposal_status": proposal.status,
                "proposal_id": proposal.correlation.proposal_id,
            }
        workspace.append_log(
            f"MCP submitted task `{task}` as {len(actions)} pending action(s): "
            + ", ".join(f"`{action.id}`" for action in actions),
            actor="mcp",
        )
        return {
            "ok": True,
            "message": proposal.message,
            "agent_output": agent_output.model_dump(
                mode="json", by_alias=True
            ),
            "feedback": [],
            "proposal_status": proposal.status,
            "proposal_id": proposal.correlation.proposal_id,
        }

    def get_state(self) -> dict[str, Any]:
        workspace = self._workspace()
        actions = workspace.read_actions()
        claim_owners = workspace.read_action_claim_owners()
        feedback = workspace.read_feedback()
        return {
            "capabilities": workspace.read_capabilities(),
            "world": workspace.read_world(),
            "actions": actions,
            "feedback": feedback,
            "safety": workspace.read_safety(),
            "plan": project_chat_plan(
                workspace.read_plan(),
                actions=actions,
                feedback=feedback,
                claim_owners=claim_owners,
            ),
        }

    def list_robots(self) -> dict[str, Any]:
        return self._workspace().read_capabilities().get("robots", {})

    def propose_action(self, action: dict[str, Any]) -> dict[str, Any]:
        """Submit an action intent without executing hardware.

        Agents SDK or MCP tool callers should use this method for tool calling.
        It only appends to the action board; watch remains the only component
        that can validate and execute pending actions.
        """

        workspace = self._workspace()
        try:
            proposal = ProposalService(workspace).propose_action_result(
                Action.model_validate(action),
                source="mcp",
                proposed_by="mcp",
            )
        except ValueError as exc:
            return {
                "ok": False,
                "message": f"Invalid action proposal: {exc}",
                "error": "invalid_proposal",
            }
        agent_output = proposal.agent_output
        parsed = agent_output.actions[0]
        self._write_agent_plan(workspace, parsed.reason or parsed.id, agent_output)
        workspace.append_log(
            f"MCP proposed action `{parsed.id}`.",
            actor="mcp",
        )
        return {
            "ok": True,
            "message": proposal.message,
            "action_id": parsed.id,
            "agent_output": agent_output.model_dump(mode="json", by_alias=True),
        }

    def tool_specs(self) -> list[dict[str, Any]]:
        """Return safe tool specs for agent frameworks.

        These specs intentionally expose proposal-only tools. They do not load
        drivers, call SDKs, or execute hardware.
        """

        return [
            {
                "type": "function",
                "name": "physical_agent_submit_task",
                "strict": True,
                "description": (
                    "Convert a human task into proposed actions in the action board. "
                    "Does not execute hardware; watch performs safety validation."
                ),
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["task"],
                    "properties": {"task": {"type": "string"}},
                },
            },
            {
                "type": "function",
                "name": "physical_agent_propose_action",
                "strict": True,
                "description": (
                    "Append one structured action intent to the action board. "
                    "Does not execute hardware; watch performs safety validation."
                ),
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "robot", "capability", "params", "reason", "depends_on"],
                    "properties": {
                        "id": {"type": "string"},
                        "robot": {"type": "string"},
                        "capability": {"type": "string"},
                        "params": {"type": "object", "additionalProperties": True},
                        "reason": {"type": "string"},
                        "depends_on": {"type": "array", "items": {"type": "string"}},
                        "metadata": {
                            "type": "object",
                            "additionalProperties": True,
                            "properties": {
                                "expected": EXPECTED_JSON_SCHEMA,
                                "safety_intent": SAFETY_INTENT_JSON_SCHEMA,
                            },
                        },
                    },
                },
            },
            {
                "type": "function",
                "name": "physical_agent_get_state",
                "strict": True,
                "description": (
                    "Read current workspace state for planning context. "
                    "Does not execute hardware."
                ),
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [],
                    "properties": {},
                },
            },
        ]

    def _workspace(self) -> StateStore:
        return open_state_store(config_path=self.config_path)

    @staticmethod
    def _write_agent_plan(
        workspace: StateStore,
        summary: str,
        agent_output: Any,
    ) -> None:
        workspace.write_plan(
            ChatPlan(
                status=(
                    "proposed_actions" if agent_output.actions else "answered"
                ),
                intent="act" if agent_output.actions else "task",
                summary=summary,
                steps=task_graph_steps(agent_output),
                needs_watch=bool(agent_output.actions),
                agent_output=agent_output,
            )
        )
