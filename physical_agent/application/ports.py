from __future__ import annotations

from typing import Any, Protocol

from physical_agent.protocol.schemas import Action


class PlannerPort(Protocol):
    """Cognition port consumed by proposal application use cases."""

    def plan(
        self,
        *,
        task: str,
        capabilities: dict[str, Any],
        world: dict[str, Any],
    ) -> list[Action]: ...
