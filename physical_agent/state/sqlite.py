from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from physical_agent.protocol.chat_summary import compact_chat_messages
from physical_agent.protocol.schemas import Action, ChatMessage, ChatPlan, Observation
from physical_agent.protocol.workspace import Workspace
from physical_agent.state.audit import export_audit_documents, read_markdown_log_entries


DOC_SCHEMAS = {
    "task": "physical-agent/task/v1",
    "capabilities": "physical-agent/capabilities/v1",
    "world": "physical-agent/world/v1",
    "actions": "physical-agent/actions/v1",
    "feedback": "physical-agent/feedback/v1",
    "chat": "physical-agent/chat/v1",
    "plan": "physical-agent/plan/v1",
    "memory": "physical-agent/memory/v1",
    "log": "physical-agent/log/v1",
}

DOC_OWNERS = {
    "task": "human",
    "capabilities": "watch",
    "world": "watch",
    "actions": "agent",
    "feedback": "watch",
    "chat": "agent",
    "plan": "agent",
    "memory": "agent",
    "log": "system",
}

REQUIRED_TABLES = {
    "doc_state",
    "actions",
    "log_entries",
    "chat_messages",
    "memory_notes",
}


class SqliteStateStore:
    filenames = Workspace.filenames

    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        self.artifacts_path = self.path / "artifacts"
        self.db_path = self.path / "state.db"
        self._file_workspace = Workspace(self.path)

    def file(self, name: str) -> Path:
        return self.path / self.filenames[name]

    def initialize(self, *, overwrite: bool = False) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        self.artifacts_path.mkdir(parents=True, exist_ok=True)
        if overwrite:
            self._unlink_database_files()

        with self._connect() as conn:
            self._create_schema(conn)
            self._ensure_default_documents(conn)

        if overwrite or not self.file("safety").exists():
            self._file_workspace.write_safety()
        if overwrite or not self.file("log").exists():
            self.file("log").write_text(
                _render_log_file(),
                encoding="utf-8",
            )

    def exists(self) -> bool:
        if not self.path.exists() or not self.db_path.exists() or not self.file("safety").exists():
            return False
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
        except sqlite3.Error:
            return False
        return REQUIRED_TABLES.issubset({str(row["name"]) for row in rows})

    def write_task(
        self,
        task: str,
        constraints: list[str] | None = None,
        *,
        owner: str = "human",
        status: str = "active",
    ) -> None:
        revision = self._next_revision("task")
        payload = {
            "metadata": {
                "schema": DOC_SCHEMAS["task"],
                "owner": owner,
                "status": status,
                "revision": revision,
            },
            "task": task.strip() or "No active task.",
            "constraints": constraints or [],
        }
        self._replace_document("task", payload, revision=revision)

    def read_task(self) -> dict[str, Any]:
        payload = self._read_document("task")
        payload.setdefault("task", "No active task.")
        payload.setdefault("constraints", [])
        return payload

    def write_capabilities(self, robots: dict[str, Any]) -> None:
        revision = self._next_revision("capabilities")
        self._replace_document(
            "capabilities",
            {
                "metadata": self._metadata("capabilities", revision),
                "robots": _as_plain(robots),
            },
            revision=revision,
        )

    def read_capabilities(self) -> dict[str, Any]:
        payload = self._read_document("capabilities")
        payload.setdefault("robots", {})
        return payload

    def write_world(self, observation: Observation | dict[str, Any]) -> None:
        value = _coerce_observation(observation)
        revision = self._next_revision("world")
        state = {
            "robots": value.robots,
            "objects": value.objects,
            "environment": value.environment,
            "artifacts": value.artifacts,
            "raw": value.raw,
        }
        self._replace_document(
            "world",
            {
                "metadata": self._metadata("world", revision),
                "summary": value.summary,
                "state": _as_plain(state),
                "observation": value.model_dump(mode="json"),
            },
            revision=revision,
        )

    def read_world(self) -> dict[str, Any]:
        payload = self._read_document("world")
        state = payload.get("state") or {}
        summary = str(payload.get("summary") or "No observation has been recorded yet.")
        observation = Observation(
            summary=summary,
            robots=state.get("robots", {}),
            objects=state.get("objects", {}),
            environment=state.get("environment", {}),
            artifacts=state.get("artifacts", []),
            raw=state.get("raw", {}),
        )
        payload["summary"] = summary
        payload["state"] = state
        payload["observation"] = observation
        return payload

    def write_actions(
        self,
        pending: list[Action | dict[str, Any]] | None = None,
        completed: list[Action | dict[str, Any]] | None = None,
        cancelled: list[Action | dict[str, Any]] | None = None,
    ) -> None:
        with self._connect() as conn:
            revision = self._next_revision_conn(conn, "actions")
            self._replace_actions_conn(
                conn,
                pending or [],
                completed or [],
                cancelled or [],
            )
            self._upsert_document_conn(
                conn,
                "actions",
                {"metadata": self._metadata("actions", revision)},
                revision,
            )

    def read_actions(self) -> dict[str, Any]:
        with self._connect() as conn:
            metadata = self._read_metadata_conn(conn, "actions")
            return {
                "metadata": metadata,
                "pending": self._read_actions_by_status(conn, "pending"),
                "completed": self._read_actions_by_status(conn, "completed"),
                "cancelled": self._read_actions_by_status(conn, "cancelled"),
            }

    def write_feedback(
        self,
        latest: dict[str, Any] | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> None:
        revision = self._next_revision("feedback")
        self._replace_document(
            "feedback",
            {
                "metadata": self._metadata("feedback", revision),
                "latest": _as_plain(latest or {}),
                "history": _as_plain(history or []),
            },
            revision=revision,
        )

    def read_feedback(self) -> dict[str, Any]:
        payload = self._read_document("feedback")
        payload.setdefault("latest", {})
        payload.setdefault("history", [])
        return payload

    def write_safety(self, rules: dict[str, Any] | None = None) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        self._file_workspace.write_safety(rules)

    def read_safety(self) -> dict[str, Any]:
        if not self.file("safety").exists():
            self.write_safety()
        return self._file_workspace.read_safety()

    def write_chat(
        self,
        messages: list[ChatMessage | dict[str, Any]],
        *,
        running_summary: str | None = None,
        compact: bool = True,
    ) -> None:
        if running_summary is None:
            running_summary = self.read_chat().get("running_summary", "")
        summary = running_summary or ""
        output_messages = [
            item if isinstance(item, ChatMessage) else ChatMessage.model_validate(item)
            for item in messages
        ]
        if compact:
            summary, output_messages = compact_chat_messages(
                output_messages,
                running_summary=summary,
            )
        with self._connect() as conn:
            revision = self._next_revision_conn(conn, "chat")
            conn.execute("DELETE FROM chat_messages")
            for item in output_messages:
                conn.execute(
                    """
                    INSERT INTO chat_messages(role, content, created_at, metadata)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        item.role,
                        item.content,
                        item.created_at,
                        _json_dumps(item.metadata),
                    ),
                )
            self._upsert_document_conn(
                conn,
                "chat",
                {
                    "metadata": self._metadata("chat", revision),
                    "running_summary": summary,
                },
                revision,
            )

    def read_chat(self) -> dict[str, Any]:
        with self._connect() as conn:
            metadata = self._read_metadata_conn(conn, "chat")
            summary = self._read_document_conn(conn, "chat").get("running_summary", "")
            rows = conn.execute(
                """
                SELECT role, content, created_at, metadata
                FROM chat_messages
                ORDER BY id
                """
            ).fetchall()
        return {
            "metadata": metadata,
            "running_summary": str(summary or ""),
            "messages": [
                ChatMessage(
                    role=str(row["role"]),
                    content=str(row["content"]),
                    created_at=row["created_at"],
                    metadata=_json_loads(row["metadata"], default={}),
                )
                for row in rows
            ],
        }

    def append_chat_message(
        self,
        role: str,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> ChatMessage:
        messages = list(self.read_chat()["messages"])
        message = ChatMessage(
            role=role,
            content=content,
            created_at=_now(),
            metadata=metadata or {},
        )
        messages.append(message)
        self.write_chat(messages)
        return message

    def write_plan(self, plan: ChatPlan | dict[str, Any]) -> None:
        value = plan if isinstance(plan, ChatPlan) else ChatPlan.model_validate(plan)
        revision = self._next_revision("plan")
        self._replace_document(
            "plan",
            {
                "metadata": self._metadata("plan", revision),
                "plan": value.model_dump(mode="json"),
            },
            revision=revision,
        )

    def read_plan(self) -> dict[str, Any]:
        payload = self._read_document("plan")
        current = payload.get("plan") or {}
        payload["plan"] = current if isinstance(current, ChatPlan) else ChatPlan.model_validate(current)
        return payload

    def write_memory(self, notes: list[dict[str, Any]]) -> None:
        with self._connect() as conn:
            revision = self._next_revision_conn(conn, "memory")
            conn.execute("DELETE FROM memory_notes")
            for note in notes:
                conn.execute(
                    """
                    INSERT INTO memory_notes(content, source, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (
                        str(note.get("content") or ""),
                        str(note.get("source") or "chat"),
                        note.get("created_at"),
                    ),
                )
            self._upsert_document_conn(
                conn,
                "memory",
                {"metadata": self._metadata("memory", revision)},
                revision,
            )

    def read_memory(self) -> dict[str, Any]:
        with self._connect() as conn:
            metadata = self._read_metadata_conn(conn, "memory")
            rows = conn.execute(
                """
                SELECT content, source, created_at
                FROM memory_notes
                ORDER BY id
                """
            ).fetchall()
        return {
            "metadata": metadata,
            "notes": [
                {
                    key: value
                    for key, value in {
                        "content": row["content"],
                        "source": row["source"],
                        "created_at": row["created_at"],
                    }.items()
                    if value is not None
                }
                for row in rows
            ],
        }

    def append_memory_note(self, content: str, *, source: str = "chat") -> dict[str, Any]:
        note = {"content": content, "source": source, "created_at": _now()}
        with self._connect() as conn:
            revision = self._next_revision_conn(conn, "memory")
            conn.execute(
                """
                INSERT INTO memory_notes(content, source, created_at)
                VALUES (?, ?, ?)
                """,
                (note["content"], note["source"], note["created_at"]),
            )
            self._upsert_document_conn(
                conn,
                "memory",
                {"metadata": self._metadata("memory", revision)},
                revision,
            )
        return note

    def append_log(self, message: str, *, actor: str | None = None) -> None:
        timestamp = _now()
        with self._connect() as conn:
            revision = self._next_revision_conn(conn, "log")
            conn.execute(
                """
                INSERT INTO log_entries(ts, actor, message)
                VALUES (?, ?, ?)
                """,
                (timestamp, actor, message),
            )
            self._upsert_document_conn(
                conn,
                "log",
                {"metadata": self._metadata("log", revision)},
                revision,
            )
        self._file_workspace.append_log(message, actor=actor)

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
            "log": self._read_log_document(),
        }
        return export_audit_documents(
            backend="sqlite",
            workspace_path=self.path,
            documents=documents,
            safety_source=self.file("safety"),
            out_dir=out_dir,
        )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _create_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS doc_state (
                name TEXT PRIMARY KEY,
                revision INTEGER DEFAULT 1,
                payload TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS actions (
                id TEXT PRIMARY KEY,
                robot TEXT,
                capability TEXT,
                params TEXT,
                reason TEXT,
                depends_on TEXT,
                status TEXT,
                result TEXT,
                seq INTEGER,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_actions_status ON actions(status, seq)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS log_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT,
                actor TEXT,
                message TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT,
                content TEXT,
                created_at TEXT,
                metadata TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT,
                source TEXT,
                created_at TEXT
            )
            """
        )

    def _unlink_database_files(self) -> None:
        for path in (
            self.db_path,
            Path(f"{self.db_path}-wal"),
            Path(f"{self.db_path}-shm"),
        ):
            if path.exists():
                path.unlink()

    def _database_files_exist(self) -> bool:
        return any(
            path.exists()
            for path in (
                self.db_path,
                Path(f"{self.db_path}-wal"),
                Path(f"{self.db_path}-shm"),
            )
        )

    def _ensure_default_documents(self, conn: sqlite3.Connection) -> None:
        defaults = {
            "task": {
                "metadata": {
                    "schema": DOC_SCHEMAS["task"],
                    "owner": "human",
                    "status": "active",
                    "revision": 1,
                },
                "task": "No active task.",
                "constraints": [],
            },
            "capabilities": {
                "metadata": self._metadata("capabilities", 1),
                "robots": {},
            },
            "world": {
                "metadata": self._metadata("world", 1),
                "summary": "No observation has been recorded yet.",
                "state": {
                    "robots": {},
                    "objects": {},
                    "environment": {},
                    "artifacts": [],
                    "raw": {},
                },
                "observation": Observation(
                    summary="No observation has been recorded yet."
                ).model_dump(mode="json"),
            },
            "actions": {"metadata": self._metadata("actions", 1)},
            "feedback": {
                "metadata": self._metadata("feedback", 1),
                "latest": {},
                "history": [],
            },
            "chat": {
                "metadata": self._metadata("chat", 1),
                "running_summary": "",
            },
            "plan": {
                "metadata": self._metadata("plan", 1),
                "plan": ChatPlan().model_dump(mode="json"),
            },
            "memory": {"metadata": self._metadata("memory", 1)},
            "log": {"metadata": self._metadata("log", 1)},
        }
        for name, payload in defaults.items():
            exists = conn.execute(
                "SELECT 1 FROM doc_state WHERE name = ?",
                (name,),
            ).fetchone()
            if exists is None:
                self._upsert_document_conn(conn, name, payload, 1)

    def _replace_actions_conn(
        self,
        conn: sqlite3.Connection,
        pending: list[Action | dict[str, Any]],
        completed: list[Action | dict[str, Any]],
        cancelled: list[Action | dict[str, Any]],
    ) -> None:
        existing = {
            str(row["id"]): row["created_at"]
            for row in conn.execute("SELECT id, created_at FROM actions").fetchall()
        }
        conn.execute("DELETE FROM actions")
        seq = 0
        timestamp = _now()
        for status, items in (
            ("pending", pending),
            ("completed", completed),
            ("cancelled", cancelled),
        ):
            for item in items:
                seq += 1
                action = item if isinstance(item, Action) else Action.model_validate(item)
                conn.execute(
                    """
                    INSERT INTO actions(
                        id, robot, capability, params, reason, depends_on,
                        status, result, seq, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        action.id,
                        action.robot,
                        action.capability,
                        _json_dumps(action.params),
                        action.reason,
                        _json_dumps(action.depends_on),
                        status,
                        _json_dumps({}),
                        seq,
                        existing.get(action.id, timestamp),
                        timestamp,
                    ),
                )

    def _replace_actions_with_revision(
        self,
        pending: list[Action | dict[str, Any]],
        completed: list[Action | dict[str, Any]],
        cancelled: list[Action | dict[str, Any]],
        *,
        revision: int,
    ) -> None:
        with self._connect() as conn:
            self._replace_actions_conn(conn, pending, completed, cancelled)
            self._upsert_document_conn(
                conn,
                "actions",
                {"metadata": self._metadata("actions", revision)},
                revision,
            )

    def _replace_chat_with_revision(
        self,
        messages: list[ChatMessage | dict[str, Any]],
        *,
        running_summary: str,
        revision: int,
    ) -> None:
        normalized = [
            item if isinstance(item, ChatMessage) else ChatMessage.model_validate(item)
            for item in messages
        ]
        with self._connect() as conn:
            conn.execute("DELETE FROM chat_messages")
            for item in normalized:
                conn.execute(
                    """
                    INSERT INTO chat_messages(role, content, created_at, metadata)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        item.role,
                        item.content,
                        item.created_at,
                        _json_dumps(item.metadata),
                    ),
                )
            self._upsert_document_conn(
                conn,
                "chat",
                {
                    "metadata": self._metadata("chat", revision),
                    "running_summary": running_summary,
                },
                revision,
            )

    def _replace_memory_with_revision(
        self,
        notes: list[dict[str, Any]],
        *,
        revision: int,
    ) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM memory_notes")
            for note in notes:
                conn.execute(
                    """
                    INSERT INTO memory_notes(content, source, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (
                        str(note.get("content") or ""),
                        str(note.get("source") or "chat"),
                        note.get("created_at"),
                    ),
                )
            self._upsert_document_conn(
                conn,
                "memory",
                {"metadata": self._metadata("memory", revision)},
                revision,
            )

    def _replace_log_entries(self, entries: list[dict[str, Any]], *, revision: int = 1) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM log_entries")
            for entry in entries:
                conn.execute(
                    """
                    INSERT INTO log_entries(ts, actor, message)
                    VALUES (?, ?, ?)
                    """,
                    (
                        entry.get("ts"),
                        entry.get("actor"),
                        str(entry.get("message") or ""),
                    ),
                )
            self._upsert_document_conn(
                conn,
                "log",
                {"metadata": self._metadata("log", revision)},
                revision,
            )

    def _read_log_document(self) -> dict[str, Any]:
        with self._connect() as conn:
            metadata = self._read_metadata_conn(conn, "log")
            rows = conn.execute(
                """
                SELECT id, ts, actor, message
                FROM log_entries
                ORDER BY id
                """
            ).fetchall()
        return {
            "metadata": metadata,
            "entries": [
                {
                    key: value
                    for key, value in {
                        "sequence": int(row["id"]),
                        "ts": row["ts"],
                        "actor": row["actor"],
                        "message": row["message"],
                    }.items()
                    if value is not None
                }
                for row in rows
            ],
        }

    def _read_actions_by_status(
        self,
        conn: sqlite3.Connection,
        status: str,
    ) -> list[Action]:
        rows = conn.execute(
            """
            SELECT id, robot, capability, params, reason, depends_on
            FROM actions
            WHERE status = ?
            ORDER BY seq, id
            """,
            (status,),
        ).fetchall()
        return [
            Action(
                id=str(row["id"]),
                robot=str(row["robot"]),
                capability=str(row["capability"]),
                params=_json_loads(row["params"], default={}),
                reason=row["reason"],
                depends_on=_json_loads(row["depends_on"], default=[]),
            )
            for row in rows
        ]

    def _read_document(self, name: str) -> dict[str, Any]:
        with self._connect() as conn:
            return self._read_document_conn(conn, name)

    def _read_document_conn(self, conn: sqlite3.Connection, name: str) -> dict[str, Any]:
        row = conn.execute(
            "SELECT revision, payload FROM doc_state WHERE name = ?",
            (name,),
        ).fetchone()
        if row is None:
            return {"metadata": self._metadata(name, 1)}
        payload = _json_loads(row["payload"], default={})
        if not isinstance(payload, dict):
            payload = {}
        metadata = dict(payload.get("metadata") or {})
        metadata.setdefault("schema", DOC_SCHEMAS.get(name, f"physical-agent/{name}/v1"))
        metadata.setdefault("owner", DOC_OWNERS.get(name, "system"))
        metadata["revision"] = int(row["revision"] or metadata.get("revision") or 1)
        payload["metadata"] = metadata
        return payload

    def _replace_document(
        self,
        name: str,
        payload: dict[str, Any],
        *,
        revision: int | None = None,
    ) -> None:
        with self._connect() as conn:
            self._upsert_document_conn(
                conn,
                name,
                payload,
                revision or self._revision_from_payload(payload) or 1,
            )

    def _upsert_document_conn(
        self,
        conn: sqlite3.Connection,
        name: str,
        payload: dict[str, Any],
        revision: int,
    ) -> None:
        value = _as_plain(payload)
        metadata = dict(value.get("metadata") or {})
        metadata.setdefault("schema", DOC_SCHEMAS.get(name, f"physical-agent/{name}/v1"))
        metadata.setdefault("owner", DOC_OWNERS.get(name, "system"))
        metadata["revision"] = revision
        value["metadata"] = metadata
        conn.execute(
            """
            INSERT INTO doc_state(name, revision, payload, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                revision = excluded.revision,
                payload = excluded.payload,
                updated_at = excluded.updated_at
            """,
            (name, revision, _json_dumps(value), _now()),
        )

    def _read_metadata_conn(self, conn: sqlite3.Connection, name: str) -> dict[str, Any]:
        return dict(self._read_document_conn(conn, name).get("metadata") or {})

    def _next_revision(self, name: str) -> int:
        with self._connect() as conn:
            return self._next_revision_conn(conn, name)

    def _next_revision_conn(self, conn: sqlite3.Connection, name: str) -> int:
        row = conn.execute(
            "SELECT revision FROM doc_state WHERE name = ?",
            (name,),
        ).fetchone()
        if row is None:
            return 1
        try:
            return int(row["revision"]) + 1
        except (TypeError, ValueError):
            return 1

    def _metadata(self, name: str, revision: int) -> dict[str, Any]:
        return {
            "schema": DOC_SCHEMAS.get(name, f"physical-agent/{name}/v1"),
            "owner": DOC_OWNERS.get(name, "system"),
            "revision": revision,
        }

    def _revision_from_payload(self, payload: dict[str, Any]) -> int | None:
        try:
            return int((payload.get("metadata") or {}).get("revision"))
        except (TypeError, ValueError):
            return None


def migrate_markdown_workspace_to_sqlite(
    workspace_path: str | Path,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    from physical_agent.state.markdown import MarkdownStateStore

    source = MarkdownStateStore(workspace_path)
    if not source.exists():
        raise FileNotFoundError(f"Markdown workspace is not initialized at {source.path}.")

    task = source.read_task()
    capabilities = source.read_capabilities()
    world = source.read_world()
    actions = source.read_actions()
    feedback = source.read_feedback()
    source.read_safety()
    chat = source.read_chat()
    plan = source.read_plan()
    memory = source.read_memory()
    log_entries, log_metadata = read_markdown_log_entries(source.file("log"))

    target = SqliteStateStore(source.path)
    if target._database_files_exist():
        if not overwrite:
            raise FileExistsError(
                f"{target.db_path} already exists. Re-run with --overwrite to replace it."
            )
        target._unlink_database_files()

    target.initialize(overwrite=False)
    target._replace_document("task", task, revision=_payload_revision(task))
    target._replace_document("capabilities", capabilities, revision=_payload_revision(capabilities))
    target._replace_document("world", world, revision=_payload_revision(world))
    target._replace_actions_with_revision(
        actions["pending"],
        actions["completed"],
        actions["cancelled"],
        revision=_payload_revision(actions),
    )
    target._replace_document("feedback", feedback, revision=_payload_revision(feedback))
    target._replace_chat_with_revision(
        chat["messages"],
        running_summary=chat.get("running_summary", ""),
        revision=_payload_revision(chat),
    )
    target._replace_document("plan", plan, revision=_payload_revision(plan))
    target._replace_memory_with_revision(memory["notes"], revision=_payload_revision(memory))
    target._replace_log_entries(log_entries, revision=_metadata_revision(log_metadata))

    return {
        "workspace_path": str(source.path),
        "db_path": str(target.db_path),
        "actions": {
            "pending": len(actions["pending"]),
            "completed": len(actions["completed"]),
            "cancelled": len(actions["cancelled"]),
        },
        "chat_messages": len(chat["messages"]),
        "memory_notes": len(memory["notes"]),
        "log_entries": len(log_entries),
    }


def _coerce_observation(value: Observation | dict[str, Any]) -> Observation:
    if isinstance(value, Observation):
        return value
    if "state" in value:
        state = value.get("state") or {}
        return Observation(
            summary=str(value.get("summary") or ""),
            robots=state.get("robots", {}),
            objects=state.get("objects", {}),
            environment=state.get("environment", {}),
            artifacts=state.get("artifacts", []),
            raw=state.get("raw", {}),
        )
    if "observation" in value:
        observation = value["observation"]
        return observation if isinstance(observation, Observation) else Observation.model_validate(observation)
    return Observation.model_validate(value)


def _payload_revision(payload: dict[str, Any]) -> int:
    try:
        return int((payload.get("metadata") or {}).get("revision") or 1)
    except (TypeError, ValueError):
        return 1


def _metadata_revision(metadata: dict[str, Any]) -> int:
    try:
        return int(metadata.get("revision") or 1)
    except (TypeError, ValueError):
        return 1


def _as_plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, list):
        return [_as_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _as_plain(item) for key, item in value.items()}
    if isinstance(value, Path):
        return str(value)
    return value


def _json_dumps(value: Any) -> str:
    return json.dumps(_as_plain(value), ensure_ascii=False, sort_keys=False)


def _json_loads(value: str | None, *, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _render_log_file() -> str:
    return (
        "---\n"
        "schema: physical-agent/log/v1\n"
        "owner: system\n"
        "revision: 1\n"
        "---\n"
        "# Physical Agent Log\n"
    )
