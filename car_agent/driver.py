from __future__ import annotations

import asyncio
import json
import math
from typing import Any

from physical_agent.drivers import (
    Action,
    ActionResult,
    Capability,
    DriverContext,
    HealthStatus,
    Observation,
    PhysicalDriver,
)


PROTOCOL_VERSION = "moce-physical-agent/v1"
EXPECTED_DEVICE = "moce-car"
EXPECTED_PROJECT = "car_agent"
MAX_REQUEST_LINE_BYTES = 2048
MAX_RESPONSE_LINE_BYTES = 4096
FIRMWARE_WATCHDOG_TIMEOUT_S = 0.8
WATCHDOG_COVERAGE_S = FIRMWARE_WATCHDOG_TIMEOUT_S - 0.1


class CarAgentError(RuntimeError):
    """Base error for the device-specific protocol adapter."""


class CarAgentProtocolError(CarAgentError):
    """The peer violated the expected newline-JSON envelope."""


class CarAgentRemoteError(CarAgentError):
    """The device returned a stable protocol error code."""

    def __init__(self, code: str, request_id: int):
        self.code = code
        self.request_id = request_id
        super().__init__(f"car_agent remote error {code} for request {request_id}")


class CarAgentDriver(PhysicalDriver):
    """Watch-owned adapter for the Moce Level 0 car firmware."""

    def __init__(self, context: DriverContext):
        super().__init__(context)
        config = context.config
        self.host = str(config["host"])
        self.port = int(config.get("port", 8080))
        self.connect_timeout_s = float(config.get("connect_timeout_s", 2.0))
        self.request_timeout_s = float(config.get("request_timeout_s", 0.5))
        self.refresh_interval_ms = int(config.get("refresh_interval_ms", 250))
        max_abs_speed = config.get("max_abs_speed")
        max_duration_ms = config.get("max_duration_ms")
        self.max_abs_speed = (
            int(max_abs_speed) if max_abs_speed is not None else None
        )
        self.max_duration_ms = (
            int(max_duration_ms) if max_duration_ms is not None else None
        )
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._request_lock = asyncio.Lock()
        self._next_request_id = 1
        self._remote_capability_names: frozenset[str] = frozenset()
        self._health_snapshot: dict[str, Any] = {}

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        if self.connected:
            return
        try:
            async with asyncio.timeout(self.connect_timeout_s):
                reader, writer = await asyncio.open_connection(
                    self.host,
                    self.port,
                    limit=MAX_RESPONSE_LINE_BYTES,
                )
            self._reader = reader
            self._writer = writer

            health = await self._request("health")
            self._validate_identity(health)
            if not self._health_payload_ok(health):
                raise CarAgentProtocolError(
                    "car_agent reported an unhealthy WiFi or service state"
                )
            self._health_snapshot = dict(health)

            capability_result = await self._request("capabilities")
            self._remote_capability_names = self._parse_remote_capabilities(
                capability_result
            )

            # Establish a known stopped baseline before Watch publishes the
            # live capability set. This is a deactivating command, not motion.
            await self._stop()
        except BaseException:
            await self.disconnect()
            raise

    async def disconnect(self) -> None:
        writer = self._writer
        self._reader = None
        self._writer = None
        self._remote_capability_names = frozenset()
        if writer is None:
            return
        writer.close()
        try:
            async with asyncio.timeout(self.request_timeout_s):
                await writer.wait_closed()
        except (TimeoutError, ConnectionError, OSError):
            pass

    async def health(self) -> HealthStatus:
        payload = await self._request("health")
        self._validate_identity(payload)
        self._health_snapshot = dict(payload)
        ok = self._health_payload_ok(payload)
        return HealthStatus(
            ok=ok,
            message="car_agent connected" if ok else "car_agent reported unhealthy",
            details=dict(payload),
        )

    async def heartbeat(self) -> None:
        status = await self.health()
        if not status.ok:
            raise CarAgentError(status.message)

    async def observe(self) -> Observation:
        payload = await self._request("observe")
        moving = payload.get("moving") is True
        motor_cmd = payload.get("motor_cmd")
        derived_status = "moving" if moving else "idle"
        summary = (
            f"{self.context.robot_id} is moving with motor command {motor_cmd}."
            if moving
            else f"{self.context.robot_id} is stopped."
        )
        robot_state = {
            "status": derived_status,
            "moving": moving,
            "motor_cmd": motor_cmd,
            "watchdog_tripped": bool(payload.get("watchdog_tripped")),
            "tof_available": bool(payload.get("tof_available")),
            "tof_valid": bool(payload.get("tof_valid")),
            "tof_mm": payload.get("tof_mm"),
            "uptime_ms": payload.get("uptime_ms"),
            "transport": "tcp_ndjson",
            "endpoint": f"{self.host}:{self.port}",
            "bench_only": bool(self._health_snapshot.get("bench_only", True)),
        }
        return Observation(
            summary=summary,
            robots={self.context.robot_id: robot_state},
            raw={self.context.robot_id: dict(payload)},
        )

    def capabilities(self) -> list[Capability]:
        empty_params = {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
        capabilities = [
            Capability(
                name="observe",
                description="Observe the current car and TOF state.",
                params_schema=empty_params,
            ),
            Capability(
                name="stop",
                description="Brake both motors.",
                params_schema=empty_params,
            ),
        ]
        if self._motion_available():
            assert self.max_abs_speed is not None
            assert self.max_duration_ms is not None
            capabilities.insert(
                1,
                Capability(
                    name="drive_for",
                    description=(
                        "Drive both wheels at a bounded PWM command for a bounded "
                        "duration, refreshing the device watchdog and braking at the end."
                    ),
                    params_schema={
                        "type": "object",
                        "required": ["speed", "duration_ms"],
                        "properties": {
                            "speed": {
                                "type": "integer",
                                "minimum": -self.max_abs_speed,
                                "maximum": self.max_abs_speed,
                                "not": {"const": 0},
                            },
                            "duration_ms": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": self.max_duration_ms,
                            },
                        },
                        "additionalProperties": False,
                    },
                    constraints={
                        "bounds": {
                            "speed": [-self.max_abs_speed, self.max_abs_speed],
                            "duration_ms": [1, self.max_duration_ms],
                        }
                    },
                    requires_approval=True,
                    timeout_s=math.ceil(self.max_duration_ms / 1000) + 2,
                ),
            )
        return capabilities

    async def execute(self, action: Action) -> ActionResult:
        if action.capability == "observe":
            observation = await self.observe()
            return ActionResult(
                status="completed",
                message="Car observation completed.",
                result={"observation": observation.model_dump(mode="json")},
            )
        if action.capability == "stop":
            payload = await self._stop()
            return ActionResult(
                status="completed",
                message="Car motors braked.",
                result={"device_result": payload},
            )
        if action.capability == "drive_for":
            return await self._execute_drive_for(action)
        return ActionResult(
            status="failed",
            message=f"Unsupported capability: {action.capability}",
        )

    async def halt(self) -> None:
        if self.connected:
            await self._stop()

    async def _stop(self) -> dict[str, Any]:
        try:
            result = await self._request("stop")
            if result.get("status") != "completed":
                raise CarAgentProtocolError(
                    "car_agent stop response did not confirm completed status"
                )
            return result
        except BaseException:
            # An unconfirmed stop leaves physical state unknown. Invalidate
            # the transport and remote motion capability so a queued action
            # cannot renew the watchdog without a fresh handshake.
            await self.disconnect()
            raise

    def _motion_available(self) -> bool:
        return (
            self.max_abs_speed is not None
            and self.max_duration_ms is not None
            and "drive" in self._remote_capability_names
        )

    async def _execute_drive_for(self, action: Action) -> ActionResult:
        validation_error = self._drive_validation_error(action.params)
        if validation_error is not None:
            return ActionResult(
                status="failed",
                message=f"Invalid drive_for parameters: {validation_error}",
            )

        speed = int(action.params["speed"])
        duration_ms = int(action.params["duration_ms"])
        loop = asyncio.get_running_loop()
        deadline = loop.time() + duration_ms / 1000.0
        refresh_interval_s = self.refresh_interval_ms / 1000.0
        refresh_count = 0
        last_device_result: dict[str, Any] = {}
        operation_error: Exception | None = None
        cancellation: asyncio.CancelledError | None = None

        try:
            while True:
                sent_at = loop.time()
                remaining_s = deadline - sent_at
                if remaining_s <= 0:
                    if refresh_count > 0:
                        break
                    raise TimeoutError(
                        "drive_for deadline elapsed before the first drive request"
                    )
                device_result = await self._request(
                    "execute",
                    {"capability": "drive", "args": {"speed": speed}},
                    timeout_s=min(self.request_timeout_s, remaining_s),
                )
                self._validate_drive_result(device_result, speed)
                last_device_result = device_result
                refresh_count += 1
                response_received_at = loop.time()
                # The firmware applies drive before emitting its response, so
                # host send time is the earliest possible watchdog reset.
                # Measuring coverage from it remains conservative even when
                # response latency has consumed part of the 800 ms window.
                if sent_at + WATCHDOG_COVERAGE_S >= deadline:
                    delay = deadline - response_received_at
                    if delay > 0:
                        await asyncio.sleep(delay)
                    break
                next_send_at = sent_at + refresh_interval_s
                if next_send_at >= deadline:
                    delay = deadline - loop.time()
                    if delay > 0:
                        await asyncio.sleep(delay)
                    break
                delay = next_send_at - loop.time()
                if delay > 0:
                    await asyncio.sleep(delay)
        except asyncio.CancelledError as exc:
            cancellation = exc
        except Exception as exc:
            operation_error = exc

        stop_error: BaseException | None = None
        try:
            await self._stop()
        except asyncio.CancelledError as exc:
            stop_error = exc
            if cancellation is None:
                cancellation = exc
        except Exception as exc:
            stop_error = exc

        if cancellation is not None:
            raise cancellation
        if operation_error is not None:
            message = f"drive_for failed: {operation_error}"
            if stop_error is not None:
                message += f"; final stop also failed: {stop_error}"
            return ActionResult(
                status="failed",
                message=message,
                result={
                    "error_type": type(operation_error).__name__,
                    "stop_error_type": (
                        type(stop_error).__name__ if stop_error is not None else None
                    ),
                    "refresh_count": refresh_count,
                },
            )
        if stop_error is not None:
            return ActionResult(
                status="failed",
                message=f"drive_for completed but final stop failed: {stop_error}",
                result={
                    "error_type": type(stop_error).__name__,
                    "refresh_count": refresh_count,
                },
            )
        return ActionResult(
            status="completed",
            message=(
                f"Drove at speed {speed} for {duration_ms} ms and braked."
            ),
            result={
                "speed": speed,
                "duration_ms": duration_ms,
                "refresh_count": refresh_count,
                "device_result": last_device_result,
            },
        )

    def _drive_validation_error(self, params: dict[str, Any]) -> str | None:
        if not self._motion_available():
            return (
                "motion is unavailable until local safety limits are configured "
                "and the remote device declares drive"
            )
        speed = params.get("speed")
        duration_ms = params.get("duration_ms")
        if isinstance(speed, bool) or not isinstance(speed, int):
            return "speed must be a non-zero integer"
        if isinstance(duration_ms, bool) or not isinstance(duration_ms, int):
            return "duration_ms must be an integer"
        assert self.max_abs_speed is not None
        assert self.max_duration_ms is not None
        if speed == 0 or abs(speed) > self.max_abs_speed:
            return (
                f"speed must be non-zero and within "
                f"[-{self.max_abs_speed}, {self.max_abs_speed}]"
            )
        if duration_ms < 1 or duration_ms > self.max_duration_ms:
            return f"duration_ms must be within [1, {self.max_duration_ms}]"
        if set(params) != {"speed", "duration_ms"}:
            return "only speed and duration_ms are accepted"
        return None

    def _validate_drive_result(
        self,
        result: dict[str, Any],
        requested_speed: int,
    ) -> None:
        if result.get("status") != "completed":
            raise CarAgentProtocolError("drive response did not report completed status")
        if result.get("clamped") is not False:
            raise CarAgentProtocolError("drive response reported clamped speed")
        if result.get("speed") != requested_speed:
            raise CarAgentProtocolError(
                "drive response effective speed did not match the requested speed"
            )
        if result.get("motor_available") is not True:
            raise CarAgentProtocolError("drive response reported motor unavailable")

    async def _request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout_s: float | None = None,
    ) -> dict[str, Any]:
        async with self._request_lock:
            reader, writer = self._require_connection()
            request_id = self._next_request_id
            self._next_request_id += 1
            envelope: dict[str, Any] = {"id": request_id, "method": method}
            if params is not None:
                envelope["params"] = params
            encoded = json.dumps(
                envelope,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            if len(encoded) >= MAX_REQUEST_LINE_BYTES:
                raise CarAgentProtocolError(
                    f"car_agent request line must be shorter than {MAX_REQUEST_LINE_BYTES} bytes"
                )

            try:
                effective_timeout_s = (
                    self.request_timeout_s if timeout_s is None else timeout_s
                )
                async with asyncio.timeout(effective_timeout_s):
                    writer.write(encoded + b"\n")
                    await writer.drain()
                    while True:
                        line = await reader.readline()
                        if not line:
                            self._mark_connection_lost()
                            raise ConnectionError(
                                "car_agent connection closed before a matching response"
                            )
                        response = self._decode_response(line)
                        if response.get("id") != request_id:
                            # The firmware can emit additional lines for one
                            # malformed request. The echoed id is authoritative.
                            continue
                        return self._unwrap_response(response, request_id)
            except TimeoutError:
                raise TimeoutError(
                    f"car_agent request {request_id} ({method}) timed out"
                ) from None
            except (ConnectionError, OSError):
                self._mark_connection_lost()
                raise

    def _require_connection(
        self,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        if self._reader is None or self._writer is None or self._writer.is_closing():
            raise ConnectionError("car_agent is not connected")
        return self._reader, self._writer

    def _mark_connection_lost(self) -> None:
        writer = self._writer
        self._reader = None
        self._writer = None
        self._remote_capability_names = frozenset()
        if writer is not None:
            writer.close()

    def _decode_response(self, line: bytes) -> dict[str, Any]:
        try:
            response = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CarAgentProtocolError("car_agent returned invalid UTF-8 JSON") from exc
        if not isinstance(response, dict):
            raise CarAgentProtocolError("car_agent response must be a JSON object")
        return response

    def _unwrap_response(
        self,
        response: dict[str, Any],
        request_id: int,
    ) -> dict[str, Any]:
        if response.get("ok") is False:
            error = response.get("error")
            code = error.get("code") if isinstance(error, dict) else None
            if not isinstance(code, str) or not code:
                raise CarAgentProtocolError(
                    "car_agent error response omitted stable error.code"
                )
            raise CarAgentRemoteError(code, request_id)
        if response.get("ok") is not True:
            raise CarAgentProtocolError("car_agent response omitted boolean ok")
        result = response.get("result")
        if not isinstance(result, dict):
            raise CarAgentProtocolError("car_agent success response omitted result object")
        return dict(result)

    def _validate_identity(self, health: dict[str, Any]) -> None:
        expected = {
            "protocol": PROTOCOL_VERSION,
            "device": EXPECTED_DEVICE,
            "project": EXPECTED_PROJECT,
        }
        for field, expected_value in expected.items():
            actual = health.get(field)
            if actual != expected_value:
                raise CarAgentProtocolError(
                    f"car_agent {field} mismatch: expected {expected_value!r}, got {actual!r}"
                )

    @staticmethod
    def _health_payload_ok(payload: dict[str, Any]) -> bool:
        return (
            payload.get("wifi_connected") is True
            and payload.get("service_running") is True
        )

    def _parse_remote_capabilities(
        self,
        payload: dict[str, Any],
    ) -> frozenset[str]:
        entries = payload.get("capabilities")
        if not isinstance(entries, list):
            raise CarAgentProtocolError(
                "car_agent capabilities result omitted capabilities array"
            )
        names = frozenset(
            entry["name"]
            for entry in entries
            if isinstance(entry, dict) and isinstance(entry.get("name"), str)
        )
        missing = {"observe", "stop"} - names
        if missing:
            raise CarAgentProtocolError(
                f"car_agent is missing required capabilities: {sorted(missing)}"
            )
        return names
