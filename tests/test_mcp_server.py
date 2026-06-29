import yaml

from physical_agent.config import write_default_config
from physical_agent.mcp.server import PhysicalAgentMCP
from physical_agent.protocol.workspace import Workspace
from physical_agent.state import open_state_store


def test_mcp_propose_action_only_writes_pending_board(tmp_path):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["workspace"]["backend"] = "markdown"
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    workspace = Workspace(tmp_path / "workspace")
    workspace.initialize()
    mcp = PhysicalAgentMCP(config_path)

    result = mcp.propose_action(
        {
            "id": "act_mcp_001",
            "robot": "arm_1",
            "capability": "observe",
            "params": {},
            "reason": "Tool caller wants observation.",
        }
    )

    assert result["ok"] is True
    assert result["action_id"] == "act_mcp_001"
    actions = workspace.read_actions()
    assert [action.id for action in actions["pending"]] == ["act_mcp_001"]
    assert actions["completed"] == []


def test_mcp_propose_action_sqlite_only_writes_pending_board(tmp_path):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["workspace"]["backend"] = "sqlite"
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
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
        }
    )

    assert result["ok"] is True
    assert result["action_id"] == "act_mcp_sqlite"
    actions = store.read_actions()
    assert [action.id for action in actions["pending"]] == ["act_mcp_sqlite"]
    assert actions["completed"] == []
    assert actions["cancelled"] == []


def test_mcp_tool_specs_describe_proposal_only_tools(tmp_path):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    specs = PhysicalAgentMCP(config_path).tool_specs()

    names = {spec["name"] for spec in specs}
    assert "physical_agent_submit_task" in names
    assert "physical_agent_propose_action" in names
    assert "physical_agent_get_state" in names
    assert all("Does not execute hardware" in spec["description"] for spec in specs)
    assert all(spec["strict"] is True for spec in specs)
