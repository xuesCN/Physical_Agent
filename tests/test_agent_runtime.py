from __future__ import annotations

import asyncio

import yaml

from physical_agent.agent.runtime import AgentRuntime
from physical_agent.config import write_default_config
from physical_agent.protocol.schemas import Action
from physical_agent.state import open_state_store


class FixedPlanner:
    last_refusal_reason = None

    def plan(self, *, task, capabilities, world):
        return [
            Action(
                id="draft",
                robot="arm_1",
                capability="observe",
                params={},
            )
        ]


def test_agent_runtime_timeout_without_feedback_is_not_success(tmp_path):
    config_path = write_default_config(
        tmp_path / "physical-agent.yaml",
        overwrite=True,
    )
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["agent"]["feedback_timeout_s"] = 0
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    store = open_state_store(config_path=config_path)
    store.initialize()
    store.write_capabilities(
        {
            "arm_1": {
                "kind": "arm",
                "driver": "mock_arm",
                "status": "connected",
                "capabilities": [
                    {
                        "name": "observe",
                        "description": "Observe.",
                        "params_schema": {"type": "object"},
                    }
                ],
            }
        }
    )

    result = asyncio.run(
        AgentRuntime(config_path, planner=FixedPlanner()).run_task(
            "look around",
            wait_for_feedback=True,
        )
    )

    assert result["ok"] is False
    assert result["feedback"] == []
    assert result["message"] == "Task did not complete successfully."
    assert result["agent_output"]["schema"] == "physical-agent/agent-output/v1"
    assert [
        action.model_dump(mode="json") for action in result["actions"]
    ] == result["agent_output"]["actions"]
    plan = store.read_plan()["plan"]
    assert plan.agent_output is not None
    assert plan.agent_output["proposal_id"] == result["proposal_id"]


def test_agent_runtime_waits_for_verification_after_terminal_action_feedback(tmp_path):
    config_path = write_default_config(
        tmp_path / "physical-agent.yaml",
        overwrite=True,
    )
    runtime = AgentRuntime(config_path, planner=FixedPlanner())
    asyncio.run(runtime.setup())
    store = runtime.workspace
    assert store is not None
    action = Action(
        id="act_expected",
        robot="arm_1",
        capability="observe",
        metadata={
            "expected": [
                {"path": "robots.arm_1.status", "op": "eq", "value": "idle"}
            ]
        },
    )

    async def scenario():
        waiting = asyncio.create_task(
            runtime.wait_for_feedback([action], timeout_s=1)
        )
        await asyncio.sleep(0.02)
        store.append_feedback_event(
            {
                "action_id": action.id,
                "status": "completed",
                "message": "driver completed",
            }
        )
        await asyncio.sleep(0.15)
        assert waiting.done() is False
        store.append_feedback_event(
            {
                "event": "expectation_check",
                "action_id": action.id,
                "status": "verified",
                "message": "expected state observed",
            }
        )
        return await waiting

    feedback = asyncio.run(scenario())
    assert feedback[0]["status"] == "completed"
