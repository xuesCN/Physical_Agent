import asyncio
import json
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


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


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


def test_markdown_state_store_export_human_view(tmp_path):
    store = MarkdownStateStore(tmp_path / "workspace")
    store.initialize()
    store.write_task("Export the markdown state", ["keep markdown backend"])
    store.write_actions([Action(id="act_md", robot="arm_1", capability="observe")])
    store.write_chat(
        [{"role": "user", "content": "audit please"}],
        running_summary="markdown summary",
        compact=False,
    )
    store.append_memory_note("markdown memory", source="test")
    store.append_log("markdown log", actor="test")

    result = store.export_human_view()
    audit_dir = store.path / "audit"

    assert result["backend"] == "markdown"
    assert result["out_dir"] == str(audit_dir.resolve())
    assert _read_json(audit_dir / "task.json")["task"] == "Export the markdown state"
    assert _read_json(audit_dir / "actions.json")["pending"][0]["id"] == "act_md"
    assert _read_json(audit_dir / "chat.json")["running_summary"] == "markdown summary"
    assert _read_json(audit_dir / "memory.json")["notes"][0]["content"] == "markdown memory"
    assert _read_json(audit_dir / "log.json")["entries"][0]["message"] == "markdown log"
    assert (audit_dir / "SAFETY.md").read_text(encoding="utf-8") == store.file(
        "safety"
    ).read_text(encoding="utf-8")


def test_sqlite_state_store_export_human_view_reads_sqlite_state(tmp_path):
    store = SqliteStateStore(tmp_path / "workspace")
    store.initialize()
    store.write_task("Export the sqlite state", ["read from state.db"])
    store.write_actions([Action(id="act_db", robot="arm_1", capability="observe")])
    store.write_chat(
        [{"role": "user", "content": "db chat"}],
        running_summary="sqlite summary",
        compact=False,
    )
    store.write_memory([{"content": "db memory", "source": "test"}])
    store.append_log("db log", actor="test")
    store.file("actions").write_text("tampered markdown action board", encoding="utf-8")
    store.file("log").write_text("tampered markdown log", encoding="utf-8")

    result = store.export_human_view()
    audit_dir = store.path / "audit"

    assert result["backend"] == "sqlite"
    assert _read_json(audit_dir / "task.json")["task"] == "Export the sqlite state"
    assert _read_json(audit_dir / "actions.json")["pending"][0]["id"] == "act_db"
    assert _read_json(audit_dir / "chat.json")["running_summary"] == "sqlite summary"
    assert _read_json(audit_dir / "memory.json")["notes"][0]["content"] == "db memory"
    log_entries = _read_json(audit_dir / "log.json")["entries"]
    assert log_entries[0]["message"] == "db log"
    assert "tampered markdown log" not in (audit_dir / "log.json").read_text(encoding="utf-8")


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


def test_migrated_sqlite_export_contains_action_board_chat_memory_and_log(tmp_path):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    workspace = Workspace(tmp_path / "workspace")
    workspace.initialize()
    workspace.write_actions(
        [Action(id="act_pending", robot="arm_1", capability="observe")],
        [Action(id="act_completed", robot="arm_1", capability="pick")],
        [Action(id="act_cancelled", robot="arm_1", capability="place")],
    )
    workspace.write_chat(
        [{"role": "user", "content": "hello"}],
        running_summary="migrated summary",
        compact=False,
    )
    workspace.append_memory_note("migrated memory", source="test")
    workspace.append_log("migrated log", actor="test")

    migrate_result = CliRunner().invoke(
        app,
        ["migrate-md-to-sqlite", "--config", str(config_path)],
    )
    assert migrate_result.exit_code == 0, migrate_result.output

    config_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config_data["workspace"]["backend"] = "sqlite"
    config_path.write_text(yaml.safe_dump(config_data, sort_keys=False), encoding="utf-8")

    audit_dir = tmp_path / "audit"
    export_result = CliRunner().invoke(
        app,
        ["export-audit", "--config", str(config_path), "--out", str(audit_dir)],
    )

    assert export_result.exit_code == 0, export_result.output
    actions = _read_json(audit_dir / "actions.json")
    assert [action["id"] for action in actions["pending"]] == ["act_pending"]
    assert [action["id"] for action in actions["completed"]] == ["act_completed"]
    assert [action["id"] for action in actions["cancelled"]] == ["act_cancelled"]
    assert _read_json(audit_dir / "chat.json")["running_summary"] == "migrated summary"
    assert _read_json(audit_dir / "memory.json")["notes"][0]["content"] == "migrated memory"
    assert _read_json(audit_dir / "log.json")["entries"][0]["message"] == "migrated log"


def test_export_audit_cli_does_not_change_backend_or_action_board(
    tmp_path,
    monkeypatch,
):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    workspace = Workspace(tmp_path / "workspace")
    workspace.initialize()
    workspace.write_actions([Action(id="act_cli", robot="arm_1", capability="observe")])
    before_config = config_path.read_text(encoding="utf-8")
    before_actions = workspace.file("actions").read_text(encoding="utf-8")

    class ExplodingWatchRuntime:
        def __init__(self, *args, **kwargs):
            raise AssertionError("export-audit must not instantiate WatchRuntime")

    monkeypatch.setattr("physical_agent.cli.WatchRuntime", ExplodingWatchRuntime)

    result = CliRunner().invoke(
        app,
        [
            "export-audit",
            "--config",
            str(config_path),
            "--out",
            str(tmp_path / "audit"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert config_path.read_text(encoding="utf-8") == before_config
    assert workspace.file("actions").read_text(encoding="utf-8") == before_actions
    assert yaml.safe_load(before_config)["workspace"]["backend"] == "markdown"
    assert _read_json(tmp_path / "audit" / "actions.json")["pending"][0]["id"] == "act_cli"


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
