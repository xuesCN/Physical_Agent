import asyncio
import sqlite3

import yaml

from physical_agent.config import write_default_config
from physical_agent.protocol.schemas import Action
from physical_agent.protocol.workspace import Workspace
from physical_agent.state import open_state_store
from physical_agent.watch.runtime import WatchRuntime


def _write_config_backend(config_path, backend: str):
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["workspace"]["backend"] = backend
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_watch_runtime_step_executes_action(tmp_path):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _write_config_backend(config_path, "markdown")
    runtime = WatchRuntime(config_path)
    asyncio.run(runtime.setup())
    workspace = Workspace(tmp_path / "workspace")
    assert workspace.read_capabilities()["robots"]["arm_1"]["driver"] == "mock_arm"
    workspace.write_actions(
        [
            Action(
                id="act_001",
                robot="arm_1",
                capability="pick",
                params={"object_id": "red_block"},
            )
        ],
        [],
        [],
    )
    count = asyncio.run(runtime.step(setup=False))
    assert count == 1
    actions = workspace.read_actions()
    assert actions["pending"] == []
    assert actions["completed"][0].id == "act_001"
    assert workspace.read_feedback()["latest"]["status"] == "completed"


def test_watch_runtime_driver_exception_cancels_sqlite_action(tmp_path, monkeypatch):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _write_config_backend(config_path, "sqlite")

    runtime = WatchRuntime(config_path)
    asyncio.run(runtime.setup())
    store = open_state_store(config_path=config_path)
    store.write_actions(
        [
            Action(
                id="act_boom",
                robot="arm_1",
                capability="pick",
                params={"object_id": "red_block"},
            )
        ],
        [],
        [],
    )

    async def fail_execute(action):
        raise RuntimeError("boom")

    monkeypatch.setattr(runtime.loaded_drivers["arm_1"].driver, "execute", fail_execute)

    try:
        count = asyncio.run(runtime.step(setup=False))
    finally:
        asyncio.run(runtime.shutdown())

    assert count == 1
    actions = store.read_actions()
    assert actions["pending"] == []
    assert actions["completed"] == []
    assert [action.id for action in actions["cancelled"]] == ["act_boom"]
    feedback = store.read_feedback()
    assert feedback["latest"]["status"] == "failed"
    assert feedback["latest"]["action_id"] == "act_boom"
    assert "boom" in feedback["latest"]["message"]
    with sqlite3.connect(store.db_path) as conn:
        row = conn.execute(
            "SELECT status, claimed_at, claim_owner FROM actions WHERE id = ?",
            ("act_boom",),
        ).fetchone()
        log_message = conn.execute(
            """
            SELECT message
            FROM log_entries
            WHERE actor = 'watch' AND message LIKE ?
            ORDER BY id DESC
            LIMIT 1
            """,
            ("Action `act_boom` failed%",),
        ).fetchone()[0]
    assert row == ("cancelled", None, None)
    assert "Action `act_boom` failed" in log_message
    assert "boom" in log_message


def test_watch_runtime_step_calls_driver_heartbeat(tmp_path, monkeypatch):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _write_config_backend(config_path, "sqlite")
    runtime = WatchRuntime(config_path)
    asyncio.run(runtime.setup())

    calls = []

    async def heartbeat():
        calls.append("heartbeat")

    monkeypatch.setattr(runtime.loaded_drivers["arm_1"].driver, "heartbeat", heartbeat)

    try:
        count = asyncio.run(runtime.step(setup=False))
    finally:
        asyncio.run(runtime.shutdown())

    assert count == 0
    assert calls == ["heartbeat"]


def test_watch_runtime_heartbeat_failure_is_audited(tmp_path, monkeypatch):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _write_config_backend(config_path, "sqlite")
    runtime = WatchRuntime(config_path)
    asyncio.run(runtime.setup())
    store = open_state_store(config_path=config_path)

    async def heartbeat():
        raise RuntimeError("pulse lost")

    monkeypatch.setattr(runtime.loaded_drivers["arm_1"].driver, "heartbeat", heartbeat)

    try:
        count = asyncio.run(runtime.step(setup=False))
    finally:
        asyncio.run(runtime.shutdown())

    assert count == 0
    feedback = store.read_feedback()
    latest = feedback["latest"]
    assert latest["event"] == "driver_heartbeat"
    assert latest["robot_id"] == "arm_1"
    assert latest["result"]["error_type"] == "RuntimeError"
    assert latest["result"]["error_message"] == "pulse lost"
    assert "Driver heartbeat failed" in latest["message"]
    assert "arm_1" in latest["message"]

    with sqlite3.connect(store.db_path) as conn:
        log_message = conn.execute(
            """
            SELECT message
            FROM log_entries
            WHERE actor = 'watch' AND message LIKE ?
            ORDER BY id DESC
            LIMIT 1
            """,
            ("%Driver heartbeat failed%",),
        ).fetchone()[0]
    assert "RuntimeError" in log_message
    assert "pulse lost" in log_message


def test_watch_runtime_shutdown_calls_driver_halt(tmp_path, monkeypatch):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _write_config_backend(config_path, "sqlite")
    runtime = WatchRuntime(config_path)
    asyncio.run(runtime.setup())

    calls = []

    async def halt():
        calls.append("halt")

    monkeypatch.setattr(runtime.loaded_drivers["arm_1"].driver, "halt", halt)

    asyncio.run(runtime.shutdown())

    assert calls == ["halt"]


def test_watch_runtime_halt_failure_is_audited_and_shutdown_completes(tmp_path, monkeypatch):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _write_config_backend(config_path, "sqlite")
    runtime = WatchRuntime(config_path)
    asyncio.run(runtime.setup())
    store = open_state_store(config_path=config_path)

    async def halt():
        raise RuntimeError("halt jammed")

    monkeypatch.setattr(runtime.loaded_drivers["arm_1"].driver, "halt", halt)

    asyncio.run(runtime.shutdown())

    assert runtime.started is False
    feedback = store.read_feedback()
    latest = feedback["latest"]
    assert latest["event"] == "driver_halt"
    assert latest["robot_id"] == "arm_1"
    assert latest["result"]["error_type"] == "RuntimeError"
    assert latest["result"]["error_message"] == "halt jammed"
    assert "Driver halt failed" in latest["message"]

    with sqlite3.connect(store.db_path) as conn:
        log_message = conn.execute(
            """
            SELECT message
            FROM log_entries
            WHERE actor = 'watch' AND message LIKE ?
            ORDER BY id DESC
            LIMIT 1
            """,
            ("%Driver halt failed%",),
        ).fetchone()[0]
    assert "RuntimeError" in log_message
    assert "halt jammed" in log_message
