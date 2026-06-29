from __future__ import annotations

from pathlib import Path
from typing import Any

from physical_agent.agent.runtime import AgentRuntime
from physical_agent.config import DEFAULT_CONFIG_NAME
from physical_agent.protocol.schemas import Action
from physical_agent.state import StateStore, open_state_store


class PhysicalAgentMCP:
    """Lightweight MCP-shaped facade over the Markdown workspace.

    The v1 package keeps this dependency-free so MCP support does not become
    part of the critical watch/agent loop. A future adapter can expose these
    methods through a concrete MCP server library.
    """

    def __init__(self, config_path: str | Path = DEFAULT_CONFIG_NAME):
        self.config_path = Path(config_path).resolve()

    async def submit_task(self, task: str) -> dict[str, Any]:
        runtime = AgentRuntime(self.config_path)
        await runtime.setup()
        workspace = runtime._workspace()
        workspace.write_task(task, owner="human")

        capabilities = workspace.read_capabilities()
        world = workspace.read_world()
        if not capabilities.get("robots"):
            message = "No capabilities are available yet. Start `physical-agent watch` first."
            workspace.append_log(message, actor="mcp")
            return {"ok": False, "message": message, "actions": []}

        planner = runtime._resolve_planner()
        actions = planner.plan(task=task, capabilities=capabilities, world=world)
        if not actions:
            message = "No action could be planned for this task."
            workspace.append_log(message, actor="mcp")
            return {"ok": False, "message": message, "actions": []}

        actions = runtime._renumber_actions(actions, workspace)
        board = workspace.read_actions()
        workspace.write_actions(
            board["pending"] + actions,
            board["completed"],
            board["cancelled"],
        )
        workspace.append_log(
            f"MCP submitted task `{task}` as {len(actions)} pending action(s): "
            + ", ".join(f"`{action.id}`" for action in actions),
            actor="mcp",
        )
        return {
            "ok": True,
            "message": "Actions proposed in Markdown workspace; watch must validate before execution.",
            "actions": actions,
            "feedback": [],
        }

    def get_state(self) -> dict[str, Any]:
        workspace = self._workspace()
        return {
            "capabilities": workspace.read_capabilities(),
            "world": workspace.read_world(),
            "actions": workspace.read_actions(),
            "feedback": workspace.read_feedback(),
        }

    def list_robots(self) -> dict[str, Any]:
        return self._workspace().read_capabilities().get("robots", {})

    def propose_action(self, action: dict[str, Any]) -> dict[str, Any]:
        """Submit an action intent without executing hardware.

        Agents SDK or MCP tool callers should use this method for tool calling.
        It only appends to ACTIONS.md; watch remains the only component that can
        validate and execute pending actions.
        """

        workspace = self._workspace()
        actions = workspace.read_actions()
        pending = actions["pending"]
        parsed = Action.model_validate(action)
        pending.append(parsed)
        workspace.write_actions(pending, actions["completed"], actions["cancelled"])
        workspace.append_log(
            f"MCP proposed action `{parsed.id}`.",
            actor="mcp",
        )
        return {
            "ok": True,
            "message": "Action proposed in Markdown workspace; watch must validate before execution.",
            "action_id": parsed.id,
        }

    def run_action(self, action: dict[str, Any]) -> dict[str, Any]:
        """Backward-compatible alias for propose_action."""

        return self.propose_action(action)

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
                    "Convert a human task into proposed actions in ACTIONS.md. "
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
                    "Append one structured action intent to ACTIONS.md. "
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
                    },
                },
            },
            {
                "type": "function",
                "name": "physical_agent_get_state",
                "strict": True,
                "description": (
                    "Read current Markdown workspace state for planning context. "
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

