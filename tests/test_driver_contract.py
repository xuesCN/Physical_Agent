from __future__ import annotations

import asyncio

from physical_agent.drivers.base import PhysicalDriver
from physical_agent.protocol.schemas import (
    Action,
    ActionResult,
    Capability,
    DriverContext,
    HealthStatus,
    Observation,
)


class _MinimalDriver(PhysicalDriver):
    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    async def health(self) -> HealthStatus:
        return HealthStatus(ok=True)

    async def observe(self) -> Observation:
        return Observation(summary="minimal")

    def capabilities(self) -> list[Capability]:
        return []

    async def execute(self, action: Action) -> ActionResult:
        return ActionResult(status="failed", message="not implemented")


def test_driver_contract_heartbeat_and_halt_default_to_noop(tmp_path):
    driver = _MinimalDriver(
        DriverContext(
            robot_id="minimal_1",
            config={},
            workspace_path=tmp_path / "workspace",
            artifacts_path=tmp_path / "workspace" / "artifacts",
        )
    )

    assert asyncio.run(driver.heartbeat()) is None
    assert asyncio.run(driver.halt()) is None
