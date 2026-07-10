from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from physical_agent.application.plan_compiler import task_graph_steps
from physical_agent.application.output_projection import materialize_agent_output
from physical_agent.application.proposals import ProposalService, renumber_actions
from physical_agent.agent.planner import Planner
from physical_agent.agent.planner_factory import create_planner
from physical_agent.config import DEFAULT_CONFIG_NAME, PhysicalAgentConfig, load_config
from physical_agent.protocol.schemas import Action, ChatPlan
from physical_agent.state import StateStore, open_state_store


class AgentRuntime:
    def __init__(
        self,
        config_path: str | Path = DEFAULT_CONFIG_NAME,
        *,
        planner: Planner | None = None,
        planner_name: str | None = None,
        model: str | None = None,
    ):
        self.config_path = Path(config_path).resolve()
        self.base_dir = self.config_path.parent
        self.config: PhysicalAgentConfig | None = None
        self.workspace: StateStore | None = None
        self.planner = planner
        self.planner_name = planner_name
        self.model = model

    async def setup(self) -> None:
        self.config = load_config(self.config_path)
        self.workspace = open_state_store(self.config, base_dir=self.base_dir)
        if not self.workspace.exists():
            self.workspace.initialize()

    async def run_task(self, task: str, *, wait_for_feedback: bool = True) -> dict[str, Any]:
        await self.setup()
        workspace = self._workspace()
        proposal = ProposalService(
            workspace,
            planner_factory=self._resolve_planner,
        ).submit_task(
            task,
            proposed_by="agent",
        )
        actions = proposal.actions
        workspace.write_plan(
            ChatPlan(
                status="proposed_actions" if actions else "answered",
                intent="act" if actions else "task",
                summary=proposal.message,
                steps=task_graph_steps(proposal.agent_output),
                actions=actions,
                needs_watch=bool(actions),
                agent_output=proposal.agent_output,
            )
        )
        if not proposal.ok:
            workspace.append_log(proposal.message, actor="agent")
            return {
                "ok": False,
                "message": proposal.message,
                "actions": [],
                "agent_output": proposal.agent_output.model_dump(
                    mode="json", by_alias=True
                ),
                "refusal_reason": proposal.refusal_reason,
                "proposal_status": proposal.status,
                "proposal_id": proposal.correlation.proposal_id,
            }
        workspace.append_log(
            f"`physical-agent run` submitted {len(actions)} action(s): "
            + ", ".join(f"`{action.id}`" for action in actions),
            actor="agent",
        )

        if not wait_for_feedback:
            return {
                "ok": True,
                "message": proposal.message,
                "actions": actions,
                "agent_output": proposal.agent_output.model_dump(
                    mode="json", by_alias=True
                ),
                "feedback": [],
                "proposal_status": proposal.status,
                "proposal_id": proposal.correlation.proposal_id,
            }

        timeout_s = self._config().agent.feedback_timeout_s
        feedback = await self.wait_for_feedback(actions, timeout_s=timeout_s)
        materialized_output = materialize_agent_output(
            proposal.agent_output,
            actions=workspace.read_actions(),
            feedback=workspace.read_feedback(),
        )
        all_done = (
            len(feedback) == len(actions)
            and materialized_output.status == "completed"
        )
        final_message = (
            "Task completed."
            if all_done
            else "Task did not complete successfully."
        )
        workspace.write_plan(
            ChatPlan(
                status="answered" if all_done else "error",
                intent="act",
                summary=final_message,
                steps=task_graph_steps(materialized_output),
                actions=actions,
                needs_watch=False,
                agent_output=materialized_output,
            )
        )
        return {
            "ok": all_done,
            "message": final_message,
            "actions": actions,
            "agent_output": materialized_output.model_dump(
                mode="json", by_alias=True
            ),
            "feedback": feedback,
            "proposal_status": proposal.status,
            "proposal_id": proposal.correlation.proposal_id,
        }

    async def wait_for_feedback(self, actions: list[Action], *, timeout_s: int) -> list[dict[str, Any]]:
        workspace = self._workspace()
        wanted = {action.id for action in actions}
        deadline = asyncio.get_running_loop().time() + timeout_s
        terminal_statuses = {"completed", "failed", "cancelled"}
        latest_by_id: dict[str, dict[str, Any]] = {}
        verification_required = {
            action.id
            for action in actions
            if bool((action.metadata or {}).get("expected"))
        }
        verification_done: set[str] = set()
        while asyncio.get_running_loop().time() < deadline:
            feedback_doc = workspace.read_feedback()
            for item in feedback_doc.get("history", []):
                if item.get("action_id") in wanted and item.get("status") in terminal_statuses:
                    latest_by_id[item["action_id"]] = item
                if (
                    item.get("event") == "expectation_check"
                    and item.get("action_id") in verification_required
                    and item.get("status") in {"verified", "violated", "skipped"}
                ):
                    verification_done.add(str(item["action_id"]))
            if wanted.issubset(latest_by_id) and verification_required.issubset(
                verification_done
            ):
                return [latest_by_id[action.id] for action in actions]
            await asyncio.sleep(0.1)
        return [latest_by_id[action.id] for action in actions if action.id in latest_by_id]

    async def interactive(self) -> None:
        await self.setup()
        print("Physical Agent interactive mode. Press Ctrl+C or submit an empty task to exit.")
        while True:
            task = input("physical-agent> ").strip()
            if not task:
                return
            result = await self.run_task(task)
            print(result["message"])

    def _workspace(self) -> StateStore:
        if self.workspace is None:
            raise RuntimeError("AgentRuntime has not been set up.")
        return self.workspace

    def _config(self) -> PhysicalAgentConfig:
        if self.config is None:
            raise RuntimeError("AgentRuntime has not been set up.")
        return self.config

    def _resolve_planner(self) -> Planner:
        if self.planner is not None:
            return self.planner
        self.planner = create_planner(
            self._config(),
            base_dir=self.base_dir,
            planner_name=self.planner_name,
            model=self.model,
        )
        return self.planner

    def _renumber_actions(self, actions: list[Action], workspace: StateStore) -> list[Action]:
        """Compatibility wrapper; new entrypoints use ProposalService directly."""

        return renumber_actions(actions, workspace)
