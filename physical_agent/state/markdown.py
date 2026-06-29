from __future__ import annotations

from pathlib import Path
from typing import Any

from physical_agent.protocol.schemas import Action, ChatMessage, ChatPlan, Observation
from physical_agent.protocol.workspace import Workspace
from physical_agent.state.audit import export_audit_documents, read_markdown_log_document


class MarkdownStateStore:
    filenames = Workspace.filenames

    def __init__(self, path: str | Path):
        self.workspace = Workspace(path)

    @property
    def path(self) -> Path:
        return self.workspace.path

    @property
    def artifacts_path(self) -> Path:
        return self.workspace.artifacts_path

    def file(self, name: str) -> Path:
        return self.workspace.file(name)

    def initialize(self, *, overwrite: bool = False) -> None:
        self.workspace.initialize(overwrite=overwrite)

    def exists(self) -> bool:
        return self.workspace.exists()

    def write_task(
        self,
        task: str,
        constraints: list[str] | None = None,
        *,
        owner: str = "human",
        status: str = "active",
    ) -> None:
        self.workspace.write_task(task, constraints, owner=owner, status=status)

    def read_task(self) -> dict[str, Any]:
        return self.workspace.read_task()

    def write_capabilities(self, robots: dict[str, Any]) -> None:
        self.workspace.write_capabilities(robots)

    def read_capabilities(self) -> dict[str, Any]:
        return self.workspace.read_capabilities()

    def write_world(self, observation: Observation | dict[str, Any]) -> None:
        self.workspace.write_world(observation)

    def read_world(self) -> dict[str, Any]:
        return self.workspace.read_world()

    def write_actions(
        self,
        pending: list[Action | dict[str, Any]] | None = None,
        completed: list[Action | dict[str, Any]] | None = None,
        cancelled: list[Action | dict[str, Any]] | None = None,
    ) -> None:
        self.workspace.write_actions(pending, completed, cancelled)

    def read_actions(self) -> dict[str, Any]:
        return self.workspace.read_actions()

    def append_pending_action(self, action: Action | dict[str, Any]) -> Action:
        parsed = action if isinstance(action, Action) else Action.model_validate(action)
        board = self.read_actions()
        self.write_actions(
            board["pending"] + [parsed],
            board["completed"],
            board["cancelled"],
        )
        return parsed

    def claim_next_ready_action(self, *, claim_owner: str = "watch") -> Action | None:
        board = self.read_actions()
        pending = list(board["pending"])
        if not pending:
            return None
        action = pending.pop(0)
        self.write_actions(pending, board["completed"], board["cancelled"])
        return action

    def recover_stale_actions(
        self,
        max_age_s: float,
        *,
        claim_owner: str | None = None,
    ) -> int:
        return 0

    def mark_action_completed(self, action: Action | dict[str, Any]) -> None:
        self._move_action_to_terminal_status(action, "completed")

    def mark_action_cancelled(self, action: Action | dict[str, Any]) -> None:
        self._move_action_to_terminal_status(action, "cancelled")

    def write_feedback(
        self,
        latest: dict[str, Any] | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> None:
        self.workspace.write_feedback(latest, history)

    def read_feedback(self) -> dict[str, Any]:
        return self.workspace.read_feedback()

    def write_safety(self, rules: dict[str, Any] | None = None) -> None:
        self.workspace.write_safety(rules)

    def read_safety(self) -> dict[str, Any]:
        return self.workspace.read_safety()

    def write_chat(
        self,
        messages: list[ChatMessage | dict[str, Any]],
        *,
        running_summary: str | None = None,
        compact: bool = True,
    ) -> None:
        self.workspace.write_chat(messages, running_summary=running_summary, compact=compact)

    def read_chat(self) -> dict[str, Any]:
        return self.workspace.read_chat()

    def append_chat_message(
        self,
        role: str,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> ChatMessage:
        return self.workspace.append_chat_message(role, content, metadata=metadata)

    def write_plan(self, plan: ChatPlan | dict[str, Any]) -> None:
        self.workspace.write_plan(plan)

    def read_plan(self) -> dict[str, Any]:
        return self.workspace.read_plan()

    def write_memory(self, notes: list[dict[str, Any]]) -> None:
        self.workspace.write_memory(notes)

    def read_memory(self) -> dict[str, Any]:
        return self.workspace.read_memory()

    def append_memory_note(self, content: str, *, source: str = "chat") -> dict[str, Any]:
        return self.workspace.append_memory_note(content, source=source)

    def append_log(self, message: str, *, actor: str | None = None) -> None:
        self.workspace.append_log(message, actor=actor)

    def export_human_view(self, out_dir: Path | None = None) -> dict[str, Any]:
        documents = {
            "task": self.read_task(),
            "capabilities": self.read_capabilities(),
            "world": self.read_world(),
            "actions": self.read_actions(),
            "feedback": self.read_feedback(),
            "chat": self.read_chat(),
            "plan": self.read_plan(),
            "memory": self.read_memory(),
            "log": read_markdown_log_document(self.file("log")),
        }
        return export_audit_documents(
            backend="markdown",
            workspace_path=self.path,
            documents=documents,
            safety_source=self.file("safety"),
            out_dir=out_dir,
        )

    def _move_action_to_terminal_status(
        self,
        action: Action | dict[str, Any],
        status: str,
    ) -> None:
        parsed = action if isinstance(action, Action) else Action.model_validate(action)
        board = self.read_actions()
        pending = [item for item in board["pending"] if item.id != parsed.id]
        completed = [item for item in board["completed"] if item.id != parsed.id]
        cancelled = [item for item in board["cancelled"] if item.id != parsed.id]
        if status == "completed":
            completed.append(parsed)
        elif status == "cancelled":
            cancelled.append(parsed)
        else:
            raise ValueError(f"Unsupported action status: {status}")
        self.write_actions(pending, completed, cancelled)
