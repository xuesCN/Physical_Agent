from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar, Protocol, runtime_checkable

from physical_agent.protocol.schemas import Action, ChatMessage, ChatPlan, Observation


@runtime_checkable
class StateStore(Protocol):
    filenames: ClassVar[dict[str, str]]
    path: Path
    artifacts_path: Path

    def file(self, name: str) -> Path: ...

    def initialize(self, *, overwrite: bool = False) -> None: ...

    def exists(self) -> bool: ...

    def write_task(
        self,
        task: str,
        constraints: list[str] | None = None,
        *,
        owner: str = "human",
        status: str = "active",
    ) -> None: ...

    def read_task(self) -> dict[str, Any]: ...

    def write_capabilities(self, robots: dict[str, Any]) -> None: ...

    def read_capabilities(self) -> dict[str, Any]: ...

    def write_world(self, observation: Observation | dict[str, Any]) -> None: ...

    def read_world(self) -> dict[str, Any]: ...

    def write_actions(
        self,
        pending: list[Action | dict[str, Any]] | None = None,
        completed: list[Action | dict[str, Any]] | None = None,
        cancelled: list[Action | dict[str, Any]] | None = None,
    ) -> None: ...

    def read_actions(self) -> dict[str, Any]: ...

    def write_feedback(
        self,
        latest: dict[str, Any] | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> None: ...

    def read_feedback(self) -> dict[str, Any]: ...

    def write_safety(self, rules: dict[str, Any] | None = None) -> None: ...

    def read_safety(self) -> dict[str, Any]: ...

    def write_chat(
        self,
        messages: list[ChatMessage | dict[str, Any]],
        *,
        running_summary: str | None = None,
        compact: bool = True,
    ) -> None: ...

    def read_chat(self) -> dict[str, Any]: ...

    def append_chat_message(
        self,
        role: str,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> ChatMessage: ...

    def write_plan(self, plan: ChatPlan | dict[str, Any]) -> None: ...

    def read_plan(self) -> dict[str, Any]: ...

    def write_memory(self, notes: list[dict[str, Any]]) -> None: ...

    def read_memory(self) -> dict[str, Any]: ...

    def append_memory_note(self, content: str, *, source: str = "chat") -> dict[str, Any]: ...

    def append_log(self, message: str, *, actor: str | None = None) -> None: ...
