import asyncio

from physical_agent.config import write_default_config
from physical_agent.api.server import ApiController
from physical_agent.mcp.server import PhysicalAgentMCP
from physical_agent.quickstart import setup_project
from physical_agent.state import open_state_store


def test_mcp_propose_action_sqlite_only_writes_pending_board(tmp_path):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    store = open_state_store(config_path=config_path)
    store.initialize()
    mcp = PhysicalAgentMCP(config_path)

    result = mcp.propose_action(
        {
            "id": "act_mcp_sqlite",
            "robot": "arm_1",
            "capability": "observe",
            "params": {},
            "reason": "Tool caller wants observation.",
            "metadata": {
                "expected": {
                    "path": "robots.arm_1.status",
                    "op": "eq",
                    "value": "idle",
                }
            },
        }
    )

    assert result["ok"] is True
    assert result["action_id"] == "act_mcp_sqlite"
    assert result["agent_output"]["schema"] == "physical-agent/agent-output/v1"
    assert result["agent_output"]["tasks"][0]["kind"] == "safety_gate"
    actions = store.read_actions()
    assert [action.id for action in actions["pending"]] == ["act_mcp_sqlite"]
    assert actions["pending"][0].metadata["expected"][0]["path"] == "robots.arm_1.status"
    assert actions["completed"] == []
    assert actions["cancelled"] == []


def test_mcp_submit_task_exposes_actions_only_through_agent_output(tmp_path):
    config_path = tmp_path / "physical-agent.yaml"
    setup_project(config_path, publish=True)

    result = asyncio.run(PhysicalAgentMCP(config_path).submit_task("look around"))

    assert result["ok"] is True
    assert "actions" not in result
    assert [
        action["capability"] for action in result["agent_output"]["actions"]
    ] == ["observe"]
    store = open_state_store(config_path=config_path)
    assert [action.capability for action in store.read_actions()["pending"]] == [
        "observe"
    ]


def test_mcp_tool_specs_describe_proposal_only_tools(tmp_path):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    specs = PhysicalAgentMCP(config_path).tool_specs()

    names = {spec["name"] for spec in specs}
    assert "physical_agent_submit_task" in names
    assert "physical_agent_propose_action" in names
    assert "physical_agent_get_state" in names
    assert all("Does not execute hardware" in spec["description"] for spec in specs)
    assert all(spec["strict"] is True for spec in specs)
    propose_spec = next(spec for spec in specs if spec["name"] == "physical_agent_propose_action")
    metadata_schema = propose_spec["parameters"]["properties"]["metadata"]
    assert "expected" in metadata_schema["properties"]
    assert "safety_intent" in metadata_schema["properties"]


def test_mcp_get_state_includes_safety_and_compiled_plan(tmp_path):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    store = open_state_store(config_path=config_path)
    store.initialize()
    mcp = PhysicalAgentMCP(config_path)
    mcp.propose_action(
        {
            "id": "act_state",
            "robot": "arm_1",
            "capability": "observe",
            "params": {},
            "reason": "Inspect state.",
        }
    )

    state = mcp.get_state()

    assert state["safety"]["rules"]
    assert state["plan"]["plan"].agent_output is not None
    api_output = ApiController(config_path).state()["plan"]["plan"]["agent_output"]
    mcp_output = state["plan"]["plan"].agent_output
    assert api_output == mcp_output


def test_mcp_state_ignores_stale_gate_from_prior_claim_owner(tmp_path):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    store = open_state_store(config_path=config_path)
    store.initialize()
    mcp = PhysicalAgentMCP(config_path)
    assert mcp.propose_action(
        {
            "id": "act_mcp_claim",
            "robot": "arm_1",
            "capability": "observe",
            "params": {},
            "reason": "Project current claim evidence.",
        }
    )["ok"] is True
    stale = store.claim_next_ready_action(claim_owner="watch-old")
    assert stale is not None
    store.append_feedback_event(
        {
            "event": "safety_gate",
            "task_id": "task:safety_gate:act_mcp_claim",
            "action_id": "act_mcp_claim",
            "status": "passed",
            "decision": "allow",
            "actor": "watch",
            "owner": "watch",
            "executor_id": "watch-old",
            "mandatory": True,
            "policy_source": "SAFETY.md",
        }
    )
    assert store.recover_stale_actions(0, claim_owner="watch-old") == 1
    successor = store.claim_next_ready_action(claim_owner="watch-successor")
    assert successor is not None

    state = mcp.get_state()
    projected = state["plan"]["plan"].agent_output
    gate = next(task for task in projected["tasks"] if task["kind"] == "safety_gate")

    assert gate["status"] == "checking"
    assert "projection_error" not in gate["details"]
    assert "claim_owner" not in state["actions"]["in_progress"][0].model_dump(
        mode="json"
    )
    assert "claim_owner" not in projected["actions"][0]


def test_mcp_state_uses_final_claim_owner_read_to_fence_late_feedback(
    tmp_path,
    monkeypatch,
):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    store = open_state_store(config_path=config_path)
    store.initialize()
    mcp = PhysicalAgentMCP(config_path)
    assert mcp.propose_action(
        {
            "id": "act_mcp_owner_race",
            "robot": "arm_1",
            "capability": "observe",
            "params": {},
            "reason": "Fence feedback with the final owner read.",
        }
    )["ok"] is True
    stale = store.claim_next_ready_action(claim_owner="watch-old")
    assert stale is not None
    store_type = type(store)
    real_read_claim_owners = store_type.read_action_claim_owners
    owner_snapshots: list[dict[str, str]] = []

    def transition_after_stale_owner_snapshot(self):
        owners = real_read_claim_owners(self)
        if self.path == store.path and not owner_snapshots:
            owner_snapshots.append(owners)
            assert self.recover_stale_actions(0, claim_owner="watch-old") == 1
            successor = self.claim_next_ready_action(claim_owner="watch-new")
            assert successor is not None
            self.append_feedback_event(
                {
                    "event": "safety_gate",
                    "task_id": "task:safety_gate:act_mcp_owner_race",
                    "action_id": "act_mcp_owner_race",
                    "status": "passed",
                    "decision": "allow",
                    "actor": "watch",
                    "owner": "watch",
                    "executor_id": "watch-old",
                    "mandatory": True,
                    "policy_source": "SAFETY.md",
                }
            )
        return owners

    monkeypatch.setattr(
        store_type,
        "read_action_claim_owners",
        transition_after_stale_owner_snapshot,
    )

    state = mcp.get_state()
    projected = state["plan"]["plan"].agent_output
    gate = next(task for task in projected["tasks"] if task["kind"] == "safety_gate")

    assert owner_snapshots == [{"act_mcp_owner_race": "watch-old"}]
    assert real_read_claim_owners(store) == {"act_mcp_owner_race": "watch-new"}
    assert gate["status"] == "checking"
    assert "last_decision" not in gate["details"]


def test_mcp_state_uses_final_owner_gate_after_late_prior_owner_reject(tmp_path):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    store = open_state_store(config_path=config_path)
    store.initialize()
    mcp = PhysicalAgentMCP(config_path)
    assert mcp.propose_action(
        {
            "id": "act_mcp_terminal_owner",
            "robot": "arm_1",
            "capability": "observe",
            "params": {},
            "reason": "Keep terminal Gate evidence bound to the final owner.",
        }
    )["ok"] is True
    stale = store.claim_next_ready_action(claim_owner="watch-old")
    assert stale is not None
    assert store.recover_stale_actions(0, claim_owner="watch-old") == 1
    successor = store.claim_next_ready_action(claim_owner="watch-successor")
    assert successor is not None
    store.append_feedback_event(
        {
            "event": "safety_gate",
            "task_id": "task:safety_gate:act_mcp_terminal_owner",
            "action_id": "act_mcp_terminal_owner",
            "status": "passed",
            "decision": "allow",
            "actor": "watch",
            "owner": "watch",
            "executor_id": "watch-successor",
            "mandatory": True,
            "policy_source": "SAFETY.md",
        }
    )
    assert store.mark_action_completed(
        successor,
        claim_owner="watch-successor",
    ) is True
    store.append_feedback_event(
        {
            "event": "safety_gate",
            "task_id": "task:safety_gate:act_mcp_terminal_owner",
            "action_id": "act_mcp_terminal_owner",
            "status": "rejected",
            "decision": "deny",
            "actor": "watch",
            "owner": "watch",
            "executor_id": "watch-old",
            "mandatory": True,
            "policy_source": "SAFETY.md",
        }
    )

    state = mcp.get_state()
    projected = state["plan"]["plan"].agent_output
    gate = next(task for task in projected["tasks"] if task["kind"] == "safety_gate")

    assert projected["status"] == "completed"
    assert gate["status"] == "passed"
    assert gate["details"]["last_decision"]["executor_id"] == "watch-successor"
    assert "claim_owner" not in state["actions"]["completed"][0].model_dump(
        mode="json"
    )
    assert "claim_owner" not in projected["actions"][0]


def test_mcp_duplicate_action_id_returns_structured_error(tmp_path):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    store = open_state_store(config_path=config_path)
    store.initialize()
    mcp = PhysicalAgentMCP(config_path)
    action = {
        "id": "act_duplicate",
        "robot": "arm_1",
        "capability": "observe",
        "params": {},
    }

    assert mcp.propose_action(action)["ok"] is True
    duplicate = mcp.propose_action(action)

    assert duplicate["ok"] is False
    assert duplicate["error"] == "invalid_proposal"
