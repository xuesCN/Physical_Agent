from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from physical_agent.api import watch_service
import physical_agent.api.server as api_server_module
from physical_agent.api.server import ApiController, create_app
from physical_agent.config import write_default_config
from physical_agent.protocol.schemas import Observation
from physical_agent.state import open_state_store


def _client_or_skip():
    pytest.importorskip("fastapi")
    try:
        from fastapi.testclient import TestClient
    except (ImportError, RuntimeError) as exc:
        pytest.skip(f"fastapi.testclient is unavailable; install .[dev,server]: {exc}")
    return TestClient


def _prepare_store(config_path: Path):
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
                        "description": "Inspect the workspace.",
                        "params_schema": {"type": "object"},
                    },
                    {
                        "name": "pick",
                        "description": "Pick an object.",
                        "params_schema": {"type": "object"},
                    },
                    {
                        "name": "place",
                        "description": "Place an object.",
                        "params_schema": {"type": "object"},
                    },
                ],
            }
        }
    )
    store.write_world(
        Observation(
            summary="API watch events test world",
            robots={"arm_1": {"status": "idle"}},
            objects={
                "red_block": {"type": "block", "color": "red", "location": "table"},
                "tray": {"type": "tray", "location": "table"},
            },
        )
    )
    return store


def _read_sse_events(client, *, limit: int, wanted: set[str] | None = None):
    events = []
    current: dict[str, str] = {}
    response = client.get(f"/api/events?limit={limit}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    for line in response.text.splitlines():
        if line == "":
            if current:
                events.append(
                    {
                        "event": current["event"],
                        "data": json.loads(current["data"]),
                    }
                )
                current = {}
                names = {item["event"] for item in events}
                if len(events) >= limit or (wanted is not None and wanted <= names):
                    break
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event: "):
            current["event"] = line.removeprefix("event: ")
        elif line.startswith("data: "):
            current["data"] = line.removeprefix("data: ")
    return events


def test_create_app_default_does_not_start_watch_runtime(tmp_path, monkeypatch):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _prepare_store(config_path)

    calls = {"loader": 0}

    def fail_loader():
        calls["loader"] += 1
        raise AssertionError("enable_watch=False must not load WatchRuntime")

    monkeypatch.setattr(watch_service, "_load_watch_runtime_class", fail_loader)

    with TestClient(create_app(config_path, enable_watch=False)) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert calls == {"loader": 0}


def test_events_stream_returns_hello_and_state_without_watch(tmp_path, monkeypatch):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _prepare_store(config_path)

    def fail_loader():
        raise AssertionError("/api/events without watch must not load WatchRuntime")

    monkeypatch.setattr(watch_service, "_load_watch_runtime_class", fail_loader)

    with TestClient(create_app(config_path, enable_watch=False)) as client:
        events = _read_sse_events(client, limit=2)

    assert [item["event"] for item in events] == ["hello", "state"]
    hello = events[0]["data"]["payload"]
    assert hello["version"] == "0.1.0"
    assert hello["watch_enabled"] is False
    assert hello["executor"]["mode"] == "none"
    assert hello["executor"]["status"] == "stopped"
    state_payload = events[1]["data"]["payload"]
    assert state_payload["reason"] == "connect"
    assert state_payload["state"]["ready"] is True
    assert state_payload["state"]["pending_actions"] == []


def test_events_stream_emits_periodic_executor_projection_without_watch(
    tmp_path,
    monkeypatch,
):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    store = _prepare_store(config_path)
    assert store.acquire_runtime_lease(
        "watch-executor",
        "external-watch",
        ttl_s=30,
    )

    monkeypatch.setattr(api_server_module, "EXECUTOR_EVENT_INTERVAL_S", 0.001)
    with TestClient(create_app(config_path, enable_watch=False)) as client:
        events = _read_sse_events(client, limit=3)

    assert [item["event"] for item in events] == ["hello", "state", "executor"]
    executor = events[2]["data"]["payload"]["executor"]
    assert executor["mode"] == "external"
    assert executor["status"] == "active"
    assert executor["lease"]["active"] is True
    assert executor["lease"]["owner"] == "external-watch"
    assert executor["lease"]["expires_at"]


def test_state_summary_ignores_lease_renewal_timestamps():
    first = {
        "ok": True,
        "ready": True,
        "watch_enabled": True,
        "executor": {
            "mode": "embedded",
            "status": "active",
            "embedded_enabled": True,
            "lease": {
                "name": "watch-executor",
                "owner": "embedded-watch",
                "active": True,
                "expires_at": "2026-07-10T00:00:05Z",
                "updated_at": "2026-07-10T00:00:00Z",
            },
            "last_error": None,
        },
    }
    second = json.loads(json.dumps(first))
    second["executor"]["lease"]["expires_at"] = "2026-07-10T00:00:10Z"
    second["executor"]["lease"]["updated_at"] = "2026-07-10T00:00:05Z"

    first_summary = watch_service.summarize_state(first)
    second_summary = watch_service.summarize_state(second)

    assert first_summary == second_summary
    assert first_summary["executor"] == {
        "mode": "embedded",
        "status": "active",
        "embedded_enabled": True,
        "lease": {
            "active": True,
            "owner": "embedded-watch",
        },
        "last_error": None,
    }


def test_enable_watch_background_loop_publishes_step_and_error(tmp_path, monkeypatch):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _prepare_store(config_path)

    class FakeWatchRuntime:
        instances = []

        def __init__(self, config_path):
            self.config_path = Path(config_path)
            self.config = SimpleNamespace(watch=SimpleNamespace(tick_ms=1))
            self.steps = 0
            self.setup_called = False
            self.shutdown_called = False
            FakeWatchRuntime.instances.append(self)

        async def setup(self):
            self.setup_called = True

        async def step(self, *, setup=True):
            assert setup is False
            self.steps += 1
            if self.steps == 1:
                return 1
            raise RuntimeError("fake watch step failed")

        async def shutdown(self):
            self.shutdown_called = True

    monkeypatch.setattr(
        watch_service,
        "_load_watch_runtime_class",
        lambda: FakeWatchRuntime,
    )

    with TestClient(
        create_app(config_path, enable_watch=True, watch_interval_s=0.005)
    ) as client:
        time.sleep(0.05)
        events = _read_sse_events(
            client,
            limit=20,
            wanted={"watch_step", "error"},
        )

    runtime = FakeWatchRuntime.instances[0]
    assert runtime.setup_called is True
    assert runtime.shutdown_called is True
    assert runtime.steps >= 2

    names = [item["event"] for item in events]
    assert "watch_step" in names
    assert "error" in names
    watch_step = next(item for item in events if item["event"] == "watch_step")
    error = next(item for item in events if item["event"] == "error")
    assert watch_step["data"]["payload"]["executed"] == 1
    assert watch_step["data"]["payload"]["state_changed"] is True
    assert watch_step["data"]["payload"]["stats"]["gate_decisions"] == 1
    assert watch_step["data"]["payload"]["state"]["ready"] is True
    assert error["data"]["payload"]["phase"] == "watch_step"
    assert error["data"]["payload"]["error_type"] == "RuntimeError"


def test_api_watch_stops_after_fatal_executor_fencing_error(tmp_path, monkeypatch):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _prepare_store(config_path)

    class FatalLeaseError(RuntimeError):
        fatal_watch_error = True

    class FakeWatchRuntime:
        instances = []

        def __init__(self, config_path):
            self.config = SimpleNamespace(watch=SimpleNamespace(tick_ms=1))
            self.steps = 0
            self.shutdown_called = False
            FakeWatchRuntime.instances.append(self)

        async def setup(self):
            return None

        async def step(self, *, setup=True):
            self.steps += 1
            raise FatalLeaseError("executor lease lost")

        async def shutdown(self):
            self.shutdown_called = True

    monkeypatch.setattr(
        watch_service,
        "_load_watch_runtime_class",
        lambda: FakeWatchRuntime,
    )
    events = watch_service.ApiEventBroker()
    service = watch_service.ApiWatchService(
        config_path,
        events=events,
        interval_s=0.001,
    )

    async def run_service():
        await service.start()
        assert service._task is not None
        await asyncio.wait_for(service._task, timeout=0.2)
        await service.stop()

    asyncio.run(run_service())

    runtime = FakeWatchRuntime.instances[0]
    assert runtime.steps == 1
    assert runtime.shutdown_called is True
    subscription = events.subscribe()
    event = subscription.get(timeout_s=0.1)
    subscription.close()
    assert event is not None
    assert event["type"] == "error"
    assert event["payload"]["phase"] == "watch_step"


def test_api_watch_waits_for_project_init_then_starts(tmp_path, monkeypatch):
    config_path = tmp_path / "physical-agent.yaml"
    loader_calls = 0

    class FakeWatchRuntime:
        instances = []

        def __init__(self, config_path):
            self.config_path = Path(config_path)
            self.config = SimpleNamespace(watch=SimpleNamespace(tick_ms=1))
            self.shutdown_called = False
            self._watch_lease_owner = "embedded-test-owner"
            FakeWatchRuntime.instances.append(self)

        async def setup(self):
            return None

        async def step(self, *, setup=True):
            assert setup is False
            return 0

        async def shutdown(self):
            self.shutdown_called = True

    def load_runtime():
        nonlocal loader_calls
        loader_calls += 1
        return FakeWatchRuntime

    monkeypatch.setattr(watch_service, "_load_watch_runtime_class", load_runtime)
    service = watch_service.ApiWatchService(
        config_path,
        events=watch_service.ApiEventBroker(),
        interval_s=0.001,
    )

    async def run_service():
        await service.start()
        for _ in range(100):
            if service.status()["phase"] == "waiting_for_init":
                break
            await asyncio.sleep(0.001)
        assert service.status()["phase"] == "waiting_for_init"
        assert loader_calls == 0

        write_default_config(config_path, overwrite=False)
        open_state_store(config_path=config_path).initialize()
        for _ in range(200):
            if service.status()["phase"] == "active":
                break
            await asyncio.sleep(0.001)
        assert service.status()["phase"] == "active"
        assert loader_calls == 1
        await service.stop()

    asyncio.run(run_service())

    assert FakeWatchRuntime.instances[0].shutdown_called is True


def test_api_watch_quietly_stands_by_for_external_lease_then_takes_over(
    tmp_path,
    monkeypatch,
):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    store = _prepare_store(config_path)
    assert store.acquire_runtime_lease(
        "watch-executor",
        "external-watch",
        ttl_s=30,
    )
    loader_calls = 0

    class FakeWatchRuntime:
        def __init__(self, config_path):
            self.config = SimpleNamespace(watch=SimpleNamespace(tick_ms=1))
            self.store = open_state_store(config_path=config_path)
            self._watch_lease_owner = "embedded-watch"

        async def setup(self):
            assert self.store.acquire_runtime_lease(
                "watch-executor",
                self._watch_lease_owner,
                ttl_s=30,
            )

        async def step(self, *, setup=True):
            assert setup is False
            return 0

        async def shutdown(self):
            self.store.release_runtime_lease(
                "watch-executor",
                self._watch_lease_owner,
            )

    def load_runtime():
        nonlocal loader_calls
        loader_calls += 1
        return FakeWatchRuntime

    monkeypatch.setattr(watch_service, "_load_watch_runtime_class", load_runtime)
    events = watch_service.ApiEventBroker()
    service = watch_service.ApiWatchService(
        config_path,
        events=events,
        interval_s=0.001,
    )
    controller = ApiController(config_path, embedded_watch_enabled=True)
    controller.bind_watch_service(service)

    async def run_service():
        await service.start()
        for _ in range(100):
            if service.status()["phase"] == "standby":
                break
            await asyncio.sleep(0.001)
        assert service.status()["phase"] == "standby"
        assert service.status()["last_error"] is None
        assert loader_calls == 0
        executor = controller.executor_status()
        assert executor["mode"] == "external"
        assert executor["status"] == "active"
        subscription = events.subscribe(replay=True)
        assert subscription.get(timeout_s=0.01) is None
        subscription.close()

        assert store.release_runtime_lease("watch-executor", "external-watch")
        for _ in range(200):
            if service.status()["phase"] == "active":
                break
            await asyncio.sleep(0.001)
        assert service.status()["phase"] == "active"
        assert loader_calls == 1
        lease = store.read_runtime_lease("watch-executor")
        assert lease is not None
        assert lease["owner"] == "embedded-watch"
        assert controller.executor_status()["mode"] == "embedded"
        await service.stop()

    asyncio.run(run_service())


def test_api_watch_projects_invalid_config_as_error_state(tmp_path):
    config_path = tmp_path / "physical-agent.yaml"
    config_path.write_text("workspace: [invalid]\n", encoding="utf-8")
    events = watch_service.ApiEventBroker()
    service = watch_service.ApiWatchService(
        config_path,
        events=events,
        interval_s=0.001,
    )
    controller = ApiController(config_path, embedded_watch_enabled=True)
    controller.bind_watch_service(service)

    async def run_service():
        await service.start()
        for _ in range(100):
            if service.status()["phase"] == "invalid_config":
                break
            await asyncio.sleep(0.001)
        executor = controller.executor_status()
        assert executor["mode"] == "waiting_for_init"
        assert executor["status"] == "invalid_config"
        assert executor["last_error"]["phase"] == "configuration"
        assert "validation error" in executor["last_error"]["message"].lower()
        await service.stop()

    asyncio.run(run_service())


def test_api_watch_setup_failure_is_fail_stop_not_reconnect_loop(
    tmp_path,
    monkeypatch,
):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _prepare_store(config_path)
    loader_calls = 0

    class FailingWatchRuntime:
        instances = []

        def __init__(self, config_path):
            self.shutdown_called = False
            FailingWatchRuntime.instances.append(self)

        async def setup(self):
            raise RuntimeError("driver connect failed")

        async def shutdown(self):
            self.shutdown_called = True

    def load_runtime():
        nonlocal loader_calls
        loader_calls += 1
        return FailingWatchRuntime

    monkeypatch.setattr(watch_service, "_load_watch_runtime_class", load_runtime)
    events = watch_service.ApiEventBroker()
    service = watch_service.ApiWatchService(
        config_path,
        events=events,
        interval_s=0.001,
    )

    async def run_service():
        await service.start()
        assert service._task is not None
        await asyncio.wait_for(service._task, timeout=0.2)
        await asyncio.sleep(0.02)
        status = service.status()
        assert status["phase"] == "degraded"
        assert status["task_running"] is False
        assert status["last_error"]["phase"] == "setup"
        assert loader_calls == 1

        subscription = events.subscribe(replay=True)
        event = subscription.get(timeout_s=0.05)
        assert event is not None
        assert event["type"] == "error"
        assert event["payload"]["message"] == "driver connect failed"
        assert subscription.get(timeout_s=0.02) is None
        subscription.close()
        await service.stop()

    asyncio.run(run_service())

    assert FailingWatchRuntime.instances[0].shutdown_called is True


def test_http_auto_step_like_fields_do_not_start_watch(tmp_path, monkeypatch):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _prepare_store(config_path)

    def fail_loader():
        raise AssertionError("request handlers must not load WatchRuntime")

    monkeypatch.setattr(watch_service, "_load_watch_runtime_class", fail_loader)

    with TestClient(create_app(config_path, enable_watch=False)) as client:
        proposed = client.post(
            "/api/actions/propose",
            json={
                "id": "act_auto_step_ignored",
                "robot": "arm_1",
                "capability": "observe",
                "params": {},
                "reason": "auto_step must be ignored by API proposal handlers",
                "depends_on": [],
                "auto_step": True,
            },
        )
        submitted = client.post(
            "/api/tasks/submit",
            json={"task": "look around", "auto_step": True},
        )
        chat = client.post(
            "/api/chat",
            json={"message": "look around", "auto_step": True},
        )

    assert proposed.status_code == 200
    assert submitted.status_code == 200
    assert chat.status_code == 200
    assert chat.json()["executed"] == 0

    store = open_state_store(config_path=config_path)
    board = store.read_actions()
    assert [item.id for item in board["completed"]] == []
    assert [item.id for item in board["cancelled"]] == []
    assert "act_auto_step_ignored" in {item.id for item in board["pending"]}


@pytest.mark.asyncio
async def test_concurrent_api_proposals_sqlite_do_not_drop_action_ids(tmp_path):
    pytest.importorskip("fastapi")
    httpx = pytest.importorskip("httpx")
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _prepare_store(config_path)
    expected_ids = {f"act_concurrent_{index:03d}" for index in range(16)}

    transport = httpx.ASGITransport(app=create_app(config_path, enable_watch=False))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        responses = await asyncio.gather(
            *[
                client.post(
                    "/api/actions/propose",
                    json={
                        "id": action_id,
                        "robot": "arm_1",
                        "capability": "observe",
                        "params": {},
                        "reason": "concurrent API proposal",
                        "depends_on": [],
                    },
                )
                for action_id in sorted(expected_ids)
            ]
        )

    assert {response.status_code for response in responses} == {200}
    store = open_state_store(config_path=config_path)
    pending_ids = {item.id for item in store.read_actions()["pending"]}
    assert expected_ids <= pending_ids
