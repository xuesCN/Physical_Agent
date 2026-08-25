from __future__ import annotations

import asyncio
import json
from pathlib import Path
import time
from typing import Any

import pytest
import yaml

from physical_agent.config import load_config
from physical_agent.drivers.loader import load_driver
from physical_agent.protocol.schemas import Action
from physical_agent.state import open_state_store
from physical_agent.watch.runtime import WatchRuntime


CAR_DRIVER_DIR = Path("car_agent").resolve()


def _load_car_driver(tmp_path: Path, config: dict):
    return load_driver(
        robot_id="car_1",
        driver_ref=str(CAR_DRIVER_DIR),
        config=config,
        workspace_path=tmp_path / "workspace",
        artifacts_path=tmp_path / "workspace" / "artifacts",
    )


def _action(capability: str, params: dict[str, Any] | None = None) -> Action:
    return Action(
        id=f"action-{capability}",
        robot="car_1",
        capability=capability,
        params=params or {},
    )


class ScriptedCarServer:
    def __init__(self):
        self.host = "127.0.0.1"
        self.port = 0
        self.requests: list[dict[str, Any]] = []
        self.raw_lines: list[bytes] = []
        self.peer_eof_count = 0
        self.connection_count = 0
        self.identity_overrides: dict[str, Any] = {}
        self.extra_before_methods: set[str] = set()
        self.split_methods: set[str] = set()
        self.delay_methods: dict[str, float] = {}
        self.drop_response_methods: set[str] = set()
        self.remote_error_methods: dict[str, str] = {}
        self.response_envelopes: dict[str, dict[str, Any]] = {}
        self.raw_response_methods: dict[str, bytes] = {}
        self.remote_capability_names = ["drive", "stop", "observe"]
        self.drive_response_overrides: dict[str, Any] = {}
        self.stop_response_overrides: dict[str, Any] = {}
        self.drive_error_at: int | None = None
        self.drop_drive_at: int | None = None
        self.stop_error_after_count: int | None = None
        self.drive_requests: list[dict[str, Any]] = []
        self.drive_arrivals: list[float] = []
        self.stop_arrivals: list[float] = []
        self.stop_count = 0
        self.first_drive = asyncio.Event()
        self.stop_seen = asyncio.Event()
        self._server: asyncio.AbstractServer | None = None
        self._writers: set[asyncio.StreamWriter] = set()
        self._handlers: set[asyncio.Task[None]] = set()
        self._peer_eof = asyncio.Event()

    @property
    def methods(self) -> list[str]:
        return [str(request.get("method")) for request in self.requests]

    async def __aenter__(self) -> "ScriptedCarServer":
        self._server = await asyncio.start_server(self._handle, self.host, 0)
        address = self._server.sockets[0].getsockname()
        self.port = int(address[1])
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        assert self._server is not None
        self._server.close()
        await self._server.wait_closed()
        for writer in tuple(self._writers):
            writer.close()
        handlers = tuple(self._handlers)
        for handler in handlers:
            handler.cancel()
        if handlers:
            await asyncio.gather(*handlers, return_exceptions=True)

    async def wait_for_peer_eof(self) -> None:
        await asyncio.wait_for(self._peer_eof.wait(), timeout=1.0)

    async def _handle(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        task = asyncio.current_task()
        assert task is not None
        self._handlers.add(task)
        self._writers.add(writer)
        self.connection_count += 1
        try:
            while True:
                line = await reader.readline()
                if not line:
                    self.peer_eof_count += 1
                    self._peer_eof.set()
                    return
                self.raw_lines.append(line)
                request = json.loads(line.decode("utf-8"))
                self.requests.append(request)
                method = str(request.get("method"))
                if self._is_drive(request):
                    self.drive_requests.append(request)
                    self.drive_arrivals.append(time.monotonic())
                    self.first_drive.set()
                    if self.drop_drive_at == len(self.drive_requests):
                        continue
                if method == "stop":
                    self.stop_count += 1
                    self.stop_arrivals.append(time.monotonic())
                    self.stop_seen.set()
                delay = self.delay_methods.get(method)
                if delay is not None:
                    await asyncio.sleep(delay)
                if method in self.drop_response_methods:
                    continue
                if method in self.raw_response_methods:
                    writer.write(self.raw_response_methods[method])
                    await writer.drain()
                    continue
                if method in self.extra_before_methods:
                    await self._send(
                        writer,
                        {
                            "id": None,
                            "ok": False,
                            "error": {
                                "code": "REQUEST_TOO_LARGE",
                                "message": "must be ignored by id",
                            },
                        },
                    )
                if method in self.response_envelopes:
                    response = {
                        "id": request.get("id"),
                        **self.response_envelopes[method],
                    }
                else:
                    response = self._response(request)
                await self._send(
                    writer,
                    response,
                    split=method in self.split_methods,
                )
        finally:
            self._writers.discard(writer)
            self._handlers.discard(task)
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), timeout=0.2)
            except (TimeoutError, ConnectionError, OSError):
                pass

    def _response(self, request: dict[str, Any]) -> dict[str, Any]:
        method = str(request.get("method"))
        if method in self.remote_error_methods:
            return {
                "id": request.get("id"),
                "ok": False,
                "error": {
                    "code": self.remote_error_methods[method],
                    "message": "ESP_ERR_INTERNAL_SECRET",
                },
            }
        if method == "health":
            result = {
                "protocol": "moce-physical-agent/v1",
                "device": "moce-car",
                "project": "car_agent",
                "firmware": "0.1.0-level0",
                "wifi_connected": True,
                "service_running": True,
                "conformance_level": 0,
                "bench_only": True,
                "peripherals": {"motor": True, "tof": True, "oled": True},
            }
            result.update(self.identity_overrides)
        elif method == "capabilities":
            result = {
                "capabilities": [
                    {"name": name, "params_schema": {"type": "object"}}
                    for name in self.remote_capability_names
                ]
            }
        elif method == "observe":
            result = {
                "status": "idle",
                "uptime_ms": 1234,
                "motor_cmd": 12,
                "moving": True,
                "watchdog_tripped": False,
                "tof_available": True,
                "tof_valid": False,
                "tof_mm": 0,
            }
        elif method == "stop":
            if (
                self.stop_error_after_count is not None
                and self.stop_count > self.stop_error_after_count
            ):
                return {
                    "id": request.get("id"),
                    "ok": False,
                    "error": {
                        "code": "EXECUTION_FAILED",
                        "message": "ESP_ERR_INTERNAL_SECRET",
                    },
                }
            result = {"status": "completed", "message": "motors braked"}
            result.update(self.stop_response_overrides)
        elif self._is_drive(request):
            if self.drive_error_at == len(self.drive_requests):
                return {
                    "id": request.get("id"),
                    "ok": False,
                    "error": {
                        "code": "EXECUTION_FAILED",
                        "message": "ESP_ERR_INTERNAL_SECRET",
                    },
                }
            args = request["params"]["args"]
            result = {
                "status": "completed",
                "speed": args["speed"],
                "clamped": False,
                "motor_available": True,
            }
            result.update(self.drive_response_overrides)
        else:
            raise AssertionError(f"Unexpected fake-server method: {method}")
        return {"id": request.get("id"), "ok": True, "result": result}

    @staticmethod
    def _is_drive(request: dict[str, Any]) -> bool:
        params = request.get("params")
        return (
            request.get("method") == "execute"
            and isinstance(params, dict)
            and params.get("capability") == "drive"
        )

    async def _send(
        self,
        writer: asyncio.StreamWriter,
        response: dict[str, Any],
        *,
        split: bool = False,
    ) -> None:
        encoded = json.dumps(response, separators=(",", ":")).encode("utf-8") + b"\n"
        if split:
            midpoint = len(encoded) // 2
            writer.write(encoded[:midpoint])
            await writer.drain()
            await asyncio.sleep(0)
            writer.write(encoded[midpoint:])
        else:
            writer.write(encoded)
        await writer.drain()


def test_car_agent_loads_without_motion_limits_and_fails_closed(tmp_path):
    loaded = _load_car_driver(tmp_path, {"host": "127.0.0.1"})

    assert type(loaded.driver).__name__ == "CarAgentDriver"
    assert [capability.name for capability in loaded.driver.capabilities()] == [
        "observe",
        "stop",
    ]


@pytest.mark.parametrize(
    "config",
    [
        {},
        {"host": ""},
        {"host": "127.0.0.1", "max_abs_speed": 10},
        {"host": "127.0.0.1", "max_duration_ms": 100},
        {
            "host": "127.0.0.1",
            "max_abs_speed": 61,
            "max_duration_ms": 100,
        },
        {
            "host": "127.0.0.1",
            "max_abs_speed": 10,
            "max_duration_ms": 28001,
        },
        {"host": "127.0.0.1", "refresh_interval_ms": 501},
        {"host": "127.0.0.1", "request_timeout_s": 0.61},
        {"host": "127.0.0.1", "unexpected": True},
    ],
)
def test_car_agent_manifest_rejects_unsafe_config_before_connect(tmp_path, config):
    with pytest.raises(ValueError):
        _load_car_driver(tmp_path, config)


def test_car_agent_protocol_lifecycle_observe_and_stop(tmp_path):
    async def scenario():
        async with ScriptedCarServer() as server:
            loaded = _load_car_driver(
                tmp_path,
                {"host": server.host, "port": server.port},
            )
            driver = loaded.driver
            await driver.connect()
            health = await driver.health()
            observation = await driver.observe()
            observe_result = await driver.execute(_action("observe"))
            stop_result = await driver.execute(_action("stop"))
            await driver.disconnect()
            await driver.disconnect()
            await server.wait_for_peer_eof()
            return server, health, observation, observe_result, stop_result

    server, health, observation, observe_result, stop_result = asyncio.run(scenario())

    assert server.connection_count == 1
    assert server.methods[:3] == ["health", "capabilities", "stop"]
    assert health.ok is True
    assert health.details["protocol"] == "moce-physical-agent/v1"
    car = observation.robots["car_1"]
    assert car["status"] == "moving"
    assert car["moving"] is True
    assert car["motor_cmd"] == 12
    assert car["tof_available"] is True
    assert car["tof_valid"] is False
    assert car["tof_mm"] == 0
    assert observe_result.status == "completed"
    assert observe_result.result["observation"]["robots"]["car_1"]["status"] == "moving"
    assert stop_result.status == "completed"
    assert server.peer_eof_count == 1


def test_car_agent_halt_stops_but_disconnect_has_no_physical_side_effect(tmp_path):
    async def scenario():
        async with ScriptedCarServer() as server:
            driver = _load_car_driver(
                tmp_path,
                {"host": server.host, "port": server.port},
            ).driver
            await driver.connect()
            stops_after_connect = server.stop_count
            await driver.halt()
            stops_after_halt = server.stop_count
            await driver.disconnect()
            await server.wait_for_peer_eof()
            return server, stops_after_connect, stops_after_halt

    server, stops_after_connect, stops_after_halt = asyncio.run(scenario())

    assert stops_after_connect == 1
    assert stops_after_halt == 2
    assert server.stop_count == stops_after_halt


def test_car_agent_connect_requires_confirmed_stopped_baseline(tmp_path):
    async def scenario():
        async with ScriptedCarServer() as server:
            server.stop_response_overrides["status"] = "failed"
            driver = _load_car_driver(
                tmp_path,
                {
                    "host": server.host,
                    "port": server.port,
                    "max_abs_speed": 12,
                    "max_duration_ms": 180,
                },
            ).driver
            try:
                with pytest.raises(RuntimeError, match="stop response"):
                    await driver.connect()
                return (
                    server,
                    driver.connected,
                    [capability.name for capability in driver.capabilities()],
                )
            finally:
                await driver.disconnect()

    server, connected, names = asyncio.run(scenario())

    assert server.methods == ["health", "capabilities", "stop"]
    assert connected is False
    assert names == ["observe", "stop"]


@pytest.mark.parametrize(
    ("field", "wrong_value"),
    [
        ("protocol", "other/v1"),
        ("device", "other-car"),
        ("project", "other-project"),
    ],
)
def test_car_agent_connect_rejects_wrong_remote_identity(tmp_path, field, wrong_value):
    async def scenario():
        async with ScriptedCarServer() as server:
            server.identity_overrides[field] = wrong_value
            driver = _load_car_driver(
                tmp_path,
                {"host": server.host, "port": server.port},
            ).driver
            with pytest.raises(RuntimeError, match=field):
                await driver.connect()
            await driver.disconnect()
            await server.wait_for_peer_eof()
            return server

    server = asyncio.run(scenario())

    assert server.methods == ["health"]


@pytest.mark.parametrize("field", ["wifi_connected", "service_running"])
def test_car_agent_connect_rejects_unhealthy_device(tmp_path, field):
    async def scenario():
        async with ScriptedCarServer() as server:
            server.identity_overrides[field] = False
            driver = _load_car_driver(
                tmp_path,
                {
                    "host": server.host,
                    "port": server.port,
                    "max_abs_speed": 12,
                    "max_duration_ms": 180,
                },
            ).driver
            try:
                with pytest.raises(RuntimeError, match="unhealthy"):
                    await driver.connect()
                names = [capability.name for capability in driver.capabilities()]
                return server, names
            finally:
                await driver.disconnect()

    server, names = asyncio.run(scenario())

    assert server.methods == ["health"]
    assert names == ["observe", "stop"]


@pytest.mark.parametrize(
    "remote_capabilities",
    [
        ["drive", "stop"],
        ["drive", "observe"],
    ],
)
def test_car_agent_connect_rejects_missing_required_remote_capability(
    tmp_path,
    remote_capabilities,
):
    async def scenario():
        async with ScriptedCarServer() as server:
            server.remote_capability_names = remote_capabilities
            driver = _load_car_driver(
                tmp_path,
                {"host": server.host, "port": server.port},
            ).driver
            with pytest.raises(RuntimeError, match="missing required capabilities"):
                await driver.connect()
            await driver.disconnect()
            return server

    server = asyncio.run(scenario())

    assert server.methods == ["health", "capabilities"]


def test_car_agent_correlates_by_id_and_handles_split_ndjson_response(tmp_path):
    async def scenario():
        async with ScriptedCarServer() as server:
            server.extra_before_methods.add("observe")
            server.split_methods.add("observe")
            driver = _load_car_driver(
                tmp_path,
                {"host": server.host, "port": server.port},
            ).driver
            await driver.connect()
            observation = await driver.observe()
            await driver.disconnect()
            return server, observation

    server, observation = asyncio.run(scenario())

    assert observation.robots["car_1"]["moving"] is True
    assert all(line.endswith(b"\n") for line in server.raw_lines)
    assert all(b"\n" not in line[:-1] for line in server.raw_lines)
    assert all(len(line) < 2048 for line in server.raw_lines)
    request_ids = [request["id"] for request in server.requests]
    assert request_ids == sorted(request_ids)
    assert len(request_ids) == len(set(request_ids))


def test_car_agent_uses_remote_error_code_not_internal_message(tmp_path):
    async def scenario():
        async with ScriptedCarServer() as server:
            driver = _load_car_driver(
                tmp_path,
                {"host": server.host, "port": server.port},
            ).driver
            await driver.connect()
            server.remote_error_methods["observe"] = "INVALID_PARAM"
            with pytest.raises(Exception) as raised:
                await driver.observe()
            await driver.disconnect()
            return raised.value

    error = asyncio.run(scenario())

    assert "INVALID_PARAM" in str(error)
    assert "ESP_ERR_INTERNAL_SECRET" not in str(error)


def test_car_agent_rejects_malformed_json_response(tmp_path):
    async def scenario():
        async with ScriptedCarServer() as server:
            driver = _load_car_driver(
                tmp_path,
                {"host": server.host, "port": server.port},
            ).driver
            try:
                await driver.connect()
                server.raw_response_methods["observe"] = b"{not-json}\n"
                with pytest.raises(RuntimeError, match="invalid UTF-8 JSON"):
                    await driver.observe()
            finally:
                await driver.disconnect()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("envelope", "message"),
    [
        ({"result": {}}, "omitted boolean ok"),
        ({"ok": True}, "omitted result object"),
        (
            {"ok": False, "error": {"message": "unstable internal text"}},
            "omitted stable error.code",
        ),
    ],
)
def test_car_agent_rejects_invalid_response_envelope(tmp_path, envelope, message):
    async def scenario():
        async with ScriptedCarServer() as server:
            driver = _load_car_driver(
                tmp_path,
                {"host": server.host, "port": server.port},
            ).driver
            try:
                await driver.connect()
                server.response_envelopes["observe"] = envelope
                with pytest.raises(RuntimeError, match=message):
                    await driver.observe()
            finally:
                await driver.disconnect()

    asyncio.run(scenario())


def test_car_agent_response_timeout_is_bounded(tmp_path):
    async def scenario():
        async with ScriptedCarServer() as server:
            driver = _load_car_driver(
                tmp_path,
                {
                    "host": server.host,
                    "port": server.port,
                    "request_timeout_s": 0.05,
                },
            ).driver
            await driver.connect()
            server.drop_response_methods.add("observe")
            started = asyncio.get_running_loop().time()
            with pytest.raises(TimeoutError):
                await driver.observe()
            elapsed = asyncio.get_running_loop().time() - started
            await driver.disconnect()
            return elapsed

    elapsed = asyncio.run(scenario())

    assert elapsed < 0.2


def test_car_agent_async_io_does_not_block_event_loop(tmp_path):
    async def scenario():
        async with ScriptedCarServer() as server:
            driver = _load_car_driver(
                tmp_path,
                {"host": server.host, "port": server.port},
            ).driver
            await driver.connect()
            observation_task: asyncio.Task | None = None
            try:
                server.delay_methods["observe"] = 0.2
                observation_task = asyncio.create_task(driver.observe())
                sentinel_finished = asyncio.Event()

                async def sentinel():
                    await asyncio.sleep(0.02)
                    sentinel_finished.set()

                sentinel_task = asyncio.create_task(sentinel())
                await asyncio.wait_for(sentinel_finished.wait(), timeout=0.1)
                assert observation_task.done() is False
                await sentinel_task
                return await observation_task
            finally:
                if observation_task is not None and not observation_task.done():
                    observation_task.cancel()
                    await asyncio.gather(observation_task, return_exceptions=True)
                await driver.disconnect()

    observation = asyncio.run(scenario())

    assert observation.robots["car_1"]["moving"] is True


def test_car_agent_disconnect_bounds_transport_close_wait(tmp_path):
    class NeverClosingWriter:
        def __init__(self):
            self.close_called = False

        def close(self):
            self.close_called = True

        async def wait_closed(self):
            await asyncio.Event().wait()

    async def scenario():
        driver = _load_car_driver(
            tmp_path,
            {"host": "unused.invalid", "request_timeout_s": 0.05},
        ).driver
        writer = NeverClosingWriter()
        driver._writer = writer
        started = asyncio.get_running_loop().time()
        await asyncio.wait_for(driver.disconnect(), timeout=0.2)
        return writer.close_called, asyncio.get_running_loop().time() - started

    close_called, elapsed = asyncio.run(scenario())

    assert close_called is True
    assert elapsed < 0.15


def test_car_agent_motion_capability_matches_configured_envelope(tmp_path):
    async def scenario():
        async with ScriptedCarServer() as server:
            driver = _load_car_driver(
                tmp_path,
                {
                    "host": server.host,
                    "port": server.port,
                    "max_abs_speed": 12,
                    "max_duration_ms": 180,
                },
            ).driver
            await driver.connect()
            capabilities = driver.capabilities()
            await driver.disconnect()
            return capabilities

    capabilities = asyncio.run(scenario())
    drive = next(capability for capability in capabilities if capability.name == "drive_for")

    assert drive.requires_approval is True
    assert drive.params_schema["required"] == ["speed", "duration_ms"]
    assert drive.params_schema["properties"]["speed"] == {
        "type": "integer",
        "minimum": -12,
        "maximum": 12,
        "not": {"const": 0},
    }
    assert drive.params_schema["properties"]["duration_ms"]["maximum"] == 180
    assert drive.constraints["bounds"] == {
        "speed": [-12, 12],
        "duration_ms": [1, 180],
    }
    assert drive.timeout_s == 3


def test_car_agent_stays_motion_disabled_after_remote_drive_discovery(tmp_path):
    async def scenario():
        async with ScriptedCarServer() as server:
            driver = _load_car_driver(
                tmp_path,
                {"host": server.host, "port": server.port},
            ).driver
            await driver.connect()
            names = [capability.name for capability in driver.capabilities()]
            await driver.disconnect()
            return names

    names = asyncio.run(scenario())

    assert names == ["observe", "stop"]


def test_car_agent_does_not_publish_motion_when_remote_drive_is_absent(tmp_path):
    async def scenario():
        async with ScriptedCarServer() as server:
            server.remote_capability_names = ["stop", "observe"]
            driver = _load_car_driver(
                tmp_path,
                {
                    "host": server.host,
                    "port": server.port,
                    "max_abs_speed": 12,
                    "max_duration_ms": 180,
                },
            ).driver
            await driver.connect()
            names = [capability.name for capability in driver.capabilities()]
            await driver.disconnect()
            return names

    names = asyncio.run(scenario())

    assert names == ["observe", "stop"]


def test_car_agent_drive_for_refreshes_before_watchdog_and_stops(tmp_path):
    async def scenario():
        async with ScriptedCarServer() as server:
            driver = _load_car_driver(
                tmp_path,
                {
                    "host": server.host,
                    "port": server.port,
                    "request_timeout_s": 0.2,
                    "refresh_interval_ms": 50,
                    "max_abs_speed": 12,
                    "max_duration_ms": 900,
                },
            ).driver
            await driver.connect()
            result = await driver.execute(
                _action("drive_for", {"speed": 8, "duration_ms": 900})
            )
            await driver.disconnect()
            return server, result

    server, result = asyncio.run(scenario())

    assert result.status == "completed"
    assert len(server.drive_requests) >= 3
    assert all(
        request["params"] == {"capability": "drive", "args": {"speed": 8}}
        for request in server.drive_requests
    )
    gaps = [
        later - earlier
        for earlier, later in zip(server.drive_arrivals, server.drive_arrivals[1:])
    ]
    assert gaps
    assert max(gaps) < 0.8
    last_drive_index = max(
        index
        for index, request in enumerate(server.requests)
        if ScriptedCarServer._is_drive(request)
    )
    assert server.requests[last_drive_index + 1]["method"] == "stop"
    assert not any(
        ScriptedCarServer._is_drive(request)
        for request in server.requests[last_drive_index + 1 :]
    )


def test_car_agent_short_drive_uses_sent_time_watchdog_coverage(tmp_path):
    async def scenario():
        async with ScriptedCarServer() as server:
            driver = _load_car_driver(
                tmp_path,
                {
                    "host": server.host,
                    "port": server.port,
                    "request_timeout_s": 0.2,
                    "refresh_interval_ms": 50,
                    "max_abs_speed": 12,
                    "max_duration_ms": 180,
                },
            ).driver
            await driver.connect()
            results = []
            for _ in range(5):
                results.append(
                    await driver.execute(
                        _action("drive_for", {"speed": 8, "duration_ms": 180})
                    )
                )
            await driver.disconnect()
            return server, results

    server, results = asyncio.run(scenario())

    assert [result.status for result in results] == ["completed"] * 5
    assert len(server.drive_requests) == 5
    assert server.requests[-1]["method"] == "stop"


def test_car_agent_drive_refresh_cadence_excludes_response_latency(tmp_path):
    async def scenario():
        async with ScriptedCarServer() as server:
            server.delay_methods["execute"] = 0.3
            driver = _load_car_driver(
                tmp_path,
                {
                    "host": server.host,
                    "port": server.port,
                    "request_timeout_s": 0.6,
                    "refresh_interval_ms": 500,
                    "max_abs_speed": 12,
                    "max_duration_ms": 1500,
                },
            ).driver
            await driver.connect()
            result = await driver.execute(
                _action("drive_for", {"speed": 8, "duration_ms": 1500})
            )
            await driver.disconnect()
            return server, result

    server, result = asyncio.run(scenario())

    gaps = [
        later - earlier
        for earlier, later in zip(server.drive_arrivals, server.drive_arrivals[1:])
    ]
    assert result.status == "completed"
    assert len(server.drive_requests) >= 3
    assert gaps
    assert max(gaps) < 0.8
    assert server.stop_arrivals[-1] - server.drive_arrivals[-1] < 0.8


def test_car_agent_drive_ack_after_deadline_fails_and_stops(tmp_path):
    async def scenario():
        async with ScriptedCarServer() as server:
            server.delay_methods["execute"] = 0.2
            driver = _load_car_driver(
                tmp_path,
                {
                    "host": server.host,
                    "port": server.port,
                    "request_timeout_s": 0.5,
                    "refresh_interval_ms": 50,
                    "max_abs_speed": 12,
                    "max_duration_ms": 180,
                },
            ).driver
            await driver.connect()
            initial_stops = server.stop_count
            result = await driver.execute(
                _action("drive_for", {"speed": 8, "duration_ms": 50})
            )
            await driver.disconnect()
            return server, initial_stops, result

    server, initial_stops, result = asyncio.run(scenario())

    assert result.status == "failed"
    assert "timed out" in result.message
    assert len(server.drive_requests) == 1
    assert server.stop_count == initial_stops + 1


@pytest.mark.parametrize(
    ("response_overrides", "drive_error_at", "drop_drive_at", "expected_text"),
    [
        ({"clamped": True}, None, None, "clamped"),
        ({"speed": 7}, None, None, "effective speed"),
        ({"motor_available": False}, None, None, "motor"),
        ({}, 1, None, "EXECUTION_FAILED"),
        ({}, None, 1, "timed out"),
    ],
)
def test_car_agent_drive_failure_still_attempts_stop(
    tmp_path,
    response_overrides,
    drive_error_at,
    drop_drive_at,
    expected_text,
):
    async def scenario():
        async with ScriptedCarServer() as server:
            server.drive_response_overrides = dict(response_overrides)
            server.drive_error_at = drive_error_at
            server.drop_drive_at = drop_drive_at
            driver = _load_car_driver(
                tmp_path,
                {
                    "host": server.host,
                    "port": server.port,
                    "request_timeout_s": 0.05,
                    "refresh_interval_ms": 50,
                    "max_abs_speed": 12,
                    "max_duration_ms": 180,
                },
            ).driver
            await driver.connect()
            initial_stops = server.stop_count
            result = await driver.execute(
                _action("drive_for", {"speed": 8, "duration_ms": 180})
            )
            await driver.disconnect()
            return server, initial_stops, result

    server, initial_stops, result = asyncio.run(scenario())

    assert result.status == "failed"
    assert expected_text in result.message
    assert server.stop_count == initial_stops + 1


def test_car_agent_drive_cancellation_propagates_after_stop(tmp_path):
    async def scenario():
        async with ScriptedCarServer() as server:
            driver = _load_car_driver(
                tmp_path,
                {
                    "host": server.host,
                    "port": server.port,
                    "request_timeout_s": 0.2,
                    "refresh_interval_ms": 200,
                    "max_abs_speed": 12,
                    "max_duration_ms": 1000,
                },
            ).driver
            await driver.connect()
            try:
                initial_stops = server.stop_count
                task = asyncio.create_task(
                    driver.execute(
                        _action("drive_for", {"speed": 8, "duration_ms": 1000})
                    )
                )
                await asyncio.wait_for(server.first_drive.wait(), timeout=0.5)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                await asyncio.wait_for(server.stop_seen.wait(), timeout=0.5)
                return server, initial_stops
            finally:
                await driver.disconnect()

    server, initial_stops = asyncio.run(scenario())

    assert server.stop_count == initial_stops + 1


def test_car_agent_final_stop_failure_makes_drive_action_fail(tmp_path):
    async def scenario():
        async with ScriptedCarServer() as server:
            driver = _load_car_driver(
                tmp_path,
                {
                    "host": server.host,
                    "port": server.port,
                    "refresh_interval_ms": 50,
                    "max_abs_speed": 12,
                    "max_duration_ms": 80,
                },
            ).driver
            await driver.connect()
            server.stop_error_after_count = server.stop_count
            result = await driver.execute(
                _action("drive_for", {"speed": 8, "duration_ms": 80})
            )
            connected_after_failure = driver.connected
            capability_names = [
                capability.name for capability in driver.capabilities()
            ]
            drive_count_after_failure = len(server.drive_requests)
            second_result = await driver.execute(
                _action("drive_for", {"speed": 8, "duration_ms": 80})
            )
            await driver.disconnect()
            return (
                server,
                result,
                connected_after_failure,
                capability_names,
                drive_count_after_failure,
                second_result,
            )

    (
        server,
        result,
        connected_after_failure,
        capability_names,
        drive_count_after_failure,
        second_result,
    ) = asyncio.run(scenario())

    assert result.status == "failed"
    assert "stop" in result.message.lower()
    assert connected_after_failure is False
    assert capability_names == ["observe", "stop"]
    assert second_result.status == "failed"
    assert len(server.drive_requests) == drive_count_after_failure


def test_car_agent_unconfirmed_stop_result_invalidates_motion(tmp_path):
    async def scenario():
        async with ScriptedCarServer() as server:
            driver = _load_car_driver(
                tmp_path,
                {
                    "host": server.host,
                    "port": server.port,
                    "max_abs_speed": 12,
                    "max_duration_ms": 180,
                },
            ).driver
            try:
                await driver.connect()
                server.stop_response_overrides["status"] = "failed"
                with pytest.raises(RuntimeError, match="stop response"):
                    await driver.execute(_action("stop"))
                return driver.connected, [
                    capability.name for capability in driver.capabilities()
                ]
            finally:
                await driver.disconnect()

    connected, names = asyncio.run(scenario())

    assert connected is False
    assert names == ["observe", "stop"]


@pytest.mark.parametrize(
    "params",
    [
        {"speed": 0, "duration_ms": 100},
        {"speed": True, "duration_ms": 100},
        {"speed": 13, "duration_ms": 100},
        {"speed": 8, "duration_ms": 181},
        {"speed": 8.5, "duration_ms": 100},
    ],
)
def test_car_agent_execute_defensively_rejects_out_of_envelope_motion(tmp_path, params):
    async def scenario():
        async with ScriptedCarServer() as server:
            driver = _load_car_driver(
                tmp_path,
                {
                    "host": server.host,
                    "port": server.port,
                    "max_abs_speed": 12,
                    "max_duration_ms": 180,
                },
            ).driver
            await driver.connect()
            result = await driver.execute(_action("drive_for", params))
            await driver.disconnect()
            return server, result

    server, result = asyncio.run(scenario())

    assert result.status == "failed"
    assert "invalid drive_for" in result.message.lower()
    assert server.drive_requests == []


def test_watch_safety_gate_rejects_out_of_bounds_car_motion_before_driver(tmp_path):
    async def scenario():
        async with ScriptedCarServer() as server:
            config_path = tmp_path / "physical-agent.yaml"
            config_path.write_text(
                yaml.safe_dump(
                    {
                        "project": {"name": "car-agent-gate-test"},
                        "workspace": {
                            "path": "./workspace",
                            "backend": "sqlite",
                        },
                        "watch": {
                            "heartbeat_enabled": False,
                            "halt_on_shutdown": True,
                            "connect_timeout_s": 1.0,
                            "observe_timeout_s": 1.0,
                            "halt_timeout_s": 1.0,
                        },
                        "robots": {
                            "car_1": {
                                "driver": str(CAR_DRIVER_DIR),
                                "execution_mode": "hardware",
                                "config": {
                                    "host": server.host,
                                    "port": server.port,
                                    "request_timeout_s": 0.2,
                                    "refresh_interval_ms": 50,
                                    "max_abs_speed": 12,
                                    "max_duration_ms": 180,
                                },
                            }
                        },
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            runtime = WatchRuntime(config_path)
            try:
                await runtime.setup()
                # ``car_1`` runs in hardware mode, so the watch loop now refuses
                # the action before SafetyGate unless SAFETY carries Agent
                # Guidance.  This test is about the Gate's bounds check, so the
                # workspace has to clear the guidance precondition first.
                store = open_state_store(config_path=config_path)
                safety_path = store.file("safety")
                safety_base = (
                    safety_path.read_text(encoding="utf-8")
                    .split("\n## Agent Guidance\n", 1)[0]
                    .rstrip()
                )
                safety_path.write_text(
                    safety_base
                    + "\n\n## Agent Guidance\n\n"
                    + "Level 0 bench use only: keep the wheels off the ground and "
                    + "stay inside the declared speed and duration envelope.\n",
                    encoding="utf-8",
                )
                execute_calls = 0
                original_execute = runtime.loaded_drivers["car_1"].driver.execute

                async def execute_spy(action):
                    nonlocal execute_calls
                    execute_calls += 1
                    return await original_execute(action)

                runtime.loaded_drivers["car_1"].driver.execute = execute_spy
                pending = store.append_pending_action(
                    Action(
                        id="act_car_out_of_bounds",
                        robot="car_1",
                        capability="drive_for",
                        params={"speed": 13, "duration_ms": 100},
                    )
                )
                approved, changed = store.approve_action(
                    pending.id,
                    actor="test_operator",
                    reason="exercise SafetyGate bounds",
                )
                assert changed is True
                assert approved.metadata["approval"]["status"] == "approved"

                executed = await runtime.step(
                    setup=False,
                    observe_when_idle=False,
                )
                actions = store.read_actions()
                feedback = store.read_feedback()["history"]
                return (
                    server,
                    runtime.last_step_stats,
                    executed,
                    actions,
                    feedback,
                    execute_calls,
                )
            finally:
                await runtime.shutdown()

    server, stats, executed, actions, feedback, execute_calls = asyncio.run(scenario())

    assert executed == 0
    assert stats["gate_decisions"] == 1
    assert [item.id for item in actions["cancelled"]] == [
        "act_car_out_of_bounds"
    ]
    gate_event = next(item for item in feedback if item.get("event") == "safety_gate")
    assert gate_event["decision"] == "deny"
    assert gate_event["policy_source"] == "SAFETY.md"
    assert "maximum of 12" in gate_event["message"]
    assert execute_calls == 0
    assert server.drive_requests == []
