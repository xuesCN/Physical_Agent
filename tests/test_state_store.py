import asyncio
import sqlite3

import pytest
import yaml
from typer.testing import CliRunner

import physical_agent.agent.chat_runtime as chat_runtime_module
import physical_agent.agent.runtime as agent_runtime_module
import physical_agent.watch.runtime as watch_runtime_module
from physical_agent.agent.chat_runtime import ChatRuntime
from physical_agent.agent.runtime import AgentRuntime
from physical_agent.cli import app
from physical_agent.config import PhysicalAgentConfig, write_default_config
from physical_agent.protocol.schemas import Action, ChatPlan, Observation
from physical_agent.protocol.workspace import Workspace
from physical_agent.state import MarkdownStateStore, SqliteStateStore, open_state_store
from physical_agent.state import factory as state_factory
from physical_agent.watch.runtime import WatchRuntime


class _NoSkills:
    def match(self, message):
        return None

    def list_skills(self):
        return []


def test_open_state_store_defaults_to_markdown(tmp_path):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)

    store = open_state_store(config_path=config_path)

    assert isinstance(store, MarkdownStateStore)
    assert store.path == (tmp_path / "workspace").resolve()


def test_open_state_store_rejects_unsupported_backend(tmp_path):
    config = PhysicalAgentConfig.model_validate(
        {"workspace": {"path": "./workspace", "backend": "unknown"}}
    )

    with pytest.raises(ValueError, match="Supported backends"):
        open_state_store(config, base_dir=tmp_path)


def test_open_state_store_sqlite_backend(tmp_path):
    config = PhysicalAgentConfig.model_validate(
        {"workspace": {"path": "./workspace", "backend": "sqlite"}}
    )

    store = open_state_store(config, base_dir=tmp_path)

    assert isinstance(store, SqliteStateStore)
    assert store.path == (tmp_path / "workspace").resolve()


def test_sqlite_state_store_protocol_roundtrip(tmp_path):
    store = SqliteStateStore(tmp_path / "workspace")
    store.initialize()

    assert store.exists()
    assert store.db_path.exists()
    assert store.file("safety").exists()

    store.write_task("Move the block", ["simulation first"], owner="human", status="active")
    assert store.read_task()["task"] == "Move the block"
    assert store.read_task()["constraints"] == ["simulation first"]

    store.write_capabilities(
        {
            "arm_1": {
                "kind": "mock",
                "driver": "mock_arm",
                "capabilities": [{"name": "observe", "params_schema": {"type": "object"}}],
            }
        }
    )
    assert store.read_capabilities()["robots"]["arm_1"]["driver"] == "mock_arm"

    store.write_world(
        Observation(
            summary="red block is on the table",
            objects={"red_block": {"location": "table"}},
        )
    )
    assert store.read_world()["state"]["objects"]["red_block"]["location"] == "table"

    pending = Action(id="act_001", robot="arm_1", capability="observe")
    completed = Action(id="act_002", robot="arm_1", capability="pick")
    cancelled = Action(id="act_003", robot="arm_1", capability="place")
    store.write_actions([pending], [completed], [cancelled])
    actions = store.read_actions()
    assert [action.id for action in actions["pending"]] == ["act_001"]
    assert [action.id for action in actions["completed"]] == ["act_002"]
    assert [action.id for action in actions["cancelled"]] == ["act_003"]

    store.write_feedback({"status": "completed"}, [{"action_id": "act_002"}])
    assert store.read_feedback()["latest"]["status"] == "completed"

    store.write_safety({"allow_autonomous_execution": False})
    assert store.read_safety()["rules"]["allow_autonomous_execution"] is False

    store.write_chat(
        [{"role": "user", "content": "older"}],
        running_summary="summary",
        compact=False,
    )
    message = store.append_chat_message("assistant", "new reply")
    assert message.content == "new reply"
    chat = store.read_chat()
    assert chat["running_summary"] == "summary"
    assert [item.content for item in chat["messages"]] == ["older", "new reply"]

    store.write_plan(ChatPlan(status="answered", intent="chat", summary="done"))
    assert store.read_plan()["plan"].summary == "done"

    store.write_memory([{"content": "prefers simulation", "source": "test"}])
    note = store.append_memory_note("likes short plans", source="chat")
    assert note["created_at"]
    assert [item["content"] for item in store.read_memory()["notes"]] == [
        "prefers simulation",
        "likes short plans",
    ]

    store.append_log("hello", actor="test")
    with sqlite3.connect(store.db_path) as conn:
        count = conn.execute("SELECT count(*) FROM log_entries").fetchone()[0]
    assert count == 1


def test_sqlite_state_store_chat_rolling_summary(tmp_path):
    store = SqliteStateStore(tmp_path / "workspace")
    store.initialize()

    for index in range(25):
        store.append_chat_message("user", f"message {index}")

    chat = store.read_chat()
    assert len(chat["messages"]) == 12
    assert [message.content for message in chat["messages"]] == [
        f"message {index}" for index in range(13, 25)
    ]
    assert "message 0" in chat["running_summary"]
    assert "message 12" in chat["running_summary"]


def test_migrate_markdown_to_sqlite_cli_does_not_switch_backend(tmp_path):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    workspace = Workspace(tmp_path / "workspace")
    workspace.initialize()
    workspace.write_task("Inspect the table", ["do not execute directly"])
    workspace.write_actions(
        [Action(id="act_001", robot="arm_1", capability="observe")],
        [Action(id="act_002", robot="arm_1", capability="pick")],
        [Action(id="act_003", robot="arm_1", capability="place")],
    )
    workspace.write_chat(
        [{"role": "user", "content": "hello"}],
        running_summary="older context",
        compact=False,
    )
    workspace.append_memory_note("remember this", source="test")
    workspace.append_log("migrated log", actor="test")

    result = CliRunner().invoke(
        app,
        ["migrate-md-to-sqlite", "--config", str(config_path)],
    )

    assert result.exit_code == 0, result.output
    assert "Config was not changed" in result.output
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["workspace"]["backend"] == "markdown"

    store = SqliteStateStore(tmp_path / "workspace")
    assert store.exists()
    assert store.read_task()["task"] == "Inspect the table"
    assert [action.id for action in store.read_actions()["pending"]] == ["act_001"]
    assert [action.id for action in store.read_actions()["completed"]] == ["act_002"]
    assert [action.id for action in store.read_actions()["cancelled"]] == ["act_003"]
    assert store.read_chat()["running_summary"] == "older context"
    assert store.read_memory()["notes"][0]["content"] == "remember this"

    with sqlite3.connect(store.db_path) as conn:
        log_count = conn.execute("SELECT count(*) FROM log_entries").fetchone()[0]
    assert log_count == 1


def test_core_runtimes_use_state_store_factory(tmp_path, monkeypatch):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    calls = {"agent": 0, "chat": 0, "watch": 0}
    real_open = state_factory.open_state_store

    def spy(name):
        def _open_state_store(*args, **kwargs):
            calls[name] += 1
            return real_open(*args, **kwargs)

        return _open_state_store

    monkeypatch.setattr(agent_runtime_module, "open_state_store", spy("agent"))
    monkeypatch.setattr(chat_runtime_module, "open_state_store", spy("chat"))
    monkeypatch.setattr(watch_runtime_module, "open_state_store", spy("watch"))

    agent = AgentRuntime(config_path)
    asyncio.run(agent.setup())
    assert isinstance(agent.workspace, MarkdownStateStore)

    chat = ChatRuntime(config_path, planner_name="rule_based")
    monkeypatch.setattr(chat, "_skill_router", lambda: _NoSkills())
    result = chat.respond("hello")
    assert result["ok"] is True
    assert isinstance(chat.workspace, MarkdownStateStore)

    watch = WatchRuntime(config_path)
    asyncio.run(watch.setup())
    try:
        assert isinstance(watch.workspace, MarkdownStateStore)
    finally:
        asyncio.run(watch.shutdown())

    assert calls == {"agent": 1, "chat": 1, "watch": 1}
