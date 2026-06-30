from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
import re
import tempfile
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from physical_agent.api.watch_service import (
    ApiEventBroker,
    ApiWatchService,
    error_payload,
    format_sse_event,
    summarize_state,
)
from physical_agent.config import DEFAULT_CONFIG_NAME, PhysicalAgentConfig, load_config
from physical_agent.ingest.files import (
    ALLOWED_TEXT_SUFFIXES,
    FileIngestionError,
    ingest_file,
    sanitize_filename,
)
from physical_agent.protocol.schemas import Action, ChatPlan
from physical_agent.state import StateStore, open_state_store


BROWSER_UPLOAD_MAX_BYTES = 5 * 1024 * 1024
UPLOAD_READ_CHUNK_BYTES = 1024 * 1024

SERVER_EXTRA_HINT = (
    "FastAPI backend dependencies are not installed. "
    "Install them with `pip install -e .[server]` or `pip install physical-agent[server]`."
)


class MissingServerDependencyError(RuntimeError):
    """Raised when the optional FastAPI server dependencies are unavailable."""


class ApiRequestError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400, details: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class ActionProposalRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    action: dict[str, Any] | None = None
    id: str | None = None
    robot: str | None = None
    capability: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    depends_on: list[str] = Field(default_factory=list)

    def action_payload(self) -> dict[str, Any]:
        if self.action is not None:
            return dict(self.action)
        data = self.model_dump(exclude_none=True, exclude={"action"})
        return data


class SubmitTaskRequest(BaseModel):
    task: str


class ChatRequest(BaseModel):
    message: str


class SearchMemoryRequest(BaseModel):
    query: str
    limit: int = 5
    tags: list[str] | str | None = None
    source_type: str | None = None


class IngestFileRequest(BaseModel):
    path: str
    tags: list[str] | str | None = None
    importance: int = 0


class ExportAuditRequest(BaseModel):
    out: str | None = None


def create_app(
    config_path: str | Path = DEFAULT_CONFIG_NAME,
    *,
    enable_watch: bool = False,
    watch_interval_s: float | None = None,
) -> Any:
    """Create the optional FastAPI app; watch is disabled unless explicitly enabled."""

    fastapi = _load_fastapi()
    FastAPI = fastapi["FastAPI"]
    File = fastapi["File"]
    Form = fastapi["Form"]
    JSONResponse = fastapi["JSONResponse"]
    PlainTextResponse = fastapi["PlainTextResponse"]
    StreamingResponse = fastapi["StreamingResponse"]
    UploadFile = fastapi["UploadFile"]

    # FastAPI resolves postponed annotations from module globals.
    globals()["UploadFile"] = UploadFile

    events = ApiEventBroker()
    controller = ApiController(config_path, events=events)

    @asynccontextmanager
    async def lifespan(app: Any) -> Any:
        app.state.events = events
        app.state.controller = controller
        app.state.watch_enabled = bool(enable_watch)
        app.state.watch_service = None
        if enable_watch:
            service = ApiWatchService(
                config_path,
                events=events,
                interval_s=watch_interval_s,
                state_provider=controller.state,
            )
            app.state.watch_service = service
            await service.start()
        try:
            yield
        finally:
            service = getattr(app.state, "watch_service", None)
            if service is not None:
                await service.stop()

    app = FastAPI(
        title="Physical Agent API",
        version="0.1.0",
        description="Proposal-only HTTP API for Physical Agent state.",
        lifespan=lifespan,
    )

    def handle_error(exc: ApiRequestError) -> Any:
        payload = {"ok": False, "message": str(exc)}
        if exc.details is not None:
            payload["details"] = _json_safe(exc.details)
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return controller.health()

    @app.get("/api/state")
    def state() -> dict[str, Any]:
        return controller.state()

    @app.get("/api/events")
    def event_stream(limit: int | None = None) -> Any:
        subscription = events.subscribe(replay=True)
        max_events = limit if limit is not None and limit > 0 else None

        def stream() -> Any:
            sent = 0

            def emit(event: dict[str, Any]) -> str:
                nonlocal sent
                sent += 1
                return format_sse_event(event)

            def should_stop() -> bool:
                return max_events is not None and sent >= max_events

            try:
                yield emit(
                    events.make_event(
                        "hello",
                        {
                            "version": "0.1.0",
                            "watch_enabled": bool(enable_watch),
                        },
                    )
                )
                if should_stop():
                    return
                yield emit(events.make_event("state", _state_event_payload(controller, "connect")))
                if should_stop():
                    return
                while True:
                    event = subscription.get(timeout_s=15.0)
                    if event is None:
                        if max_events is not None:
                            return
                        yield ": keepalive\n\n"
                        continue
                    yield emit(event)
                    if should_stop():
                        return
            finally:
                subscription.close()

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/api/actions/propose")
    def propose_action(payload: ActionProposalRequest) -> dict[str, Any]:
        try:
            return controller.propose_action(payload)
        except ApiRequestError as exc:
            return handle_error(exc)

    @app.post("/api/tasks/submit")
    def submit_task(payload: SubmitTaskRequest) -> dict[str, Any]:
        try:
            return controller.submit_task(payload)
        except ApiRequestError as exc:
            return handle_error(exc)

    @app.post("/api/chat")
    def chat(payload: ChatRequest) -> dict[str, Any]:
        try:
            return controller.chat(payload)
        except ApiRequestError as exc:
            return handle_error(exc)

    @app.post("/api/search-memory")
    def search_memory(payload: SearchMemoryRequest) -> dict[str, Any]:
        try:
            return controller.search_memory(payload)
        except ApiRequestError as exc:
            return handle_error(exc)

    @app.post("/api/ingest-file")
    def ingest_file_endpoint(payload: IngestFileRequest) -> dict[str, Any]:
        try:
            return controller.ingest_file(payload)
        except ApiRequestError as exc:
            return handle_error(exc)

    @app.post("/api/upload")
    async def upload_endpoint(
        file: UploadFile = File(...),
        tags: str | None = Form(None),
        importance: int = Form(0),
    ) -> dict[str, Any] | Any:
        try:
            return await controller.upload_file(
                file,
                tags=tags,
                importance=importance,
            )
        except ApiRequestError as exc:
            return handle_error(exc)
        finally:
            try:
                await file.close()
            except Exception:
                pass

    @app.post("/api/export-audit")
    def export_audit(payload: ExportAuditRequest) -> dict[str, Any]:
        try:
            return controller.export_audit(payload)
        except ApiRequestError as exc:
            return handle_error(exc)

    _install_frontend_routes(app, fastapi, PlainTextResponse)

    return app


class ApiController:
    def __init__(
        self,
        config_path: str | Path = DEFAULT_CONFIG_NAME,
        *,
        events: ApiEventBroker | None = None,
    ):
        self.config_path = Path(config_path).resolve()
        self.base_dir = self.config_path.parent
        self.events = events
        self.planner = SafeProposalPlanner()

    def health(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {
                "ok": False,
                "ready": False,
                "message": "Config file is missing.",
                "config_path": str(self.config_path),
                "config_exists": False,
                "workspace_exists": False,
            }
        try:
            config, store = self._store()
        except Exception as exc:
            return {
                "ok": False,
                "ready": False,
                "message": str(exc),
                "config_path": str(self.config_path),
                "config_exists": True,
                "workspace_exists": False,
            }
        exists = store.exists()
        return {
            "ok": True,
            "ready": exists,
            "message": "Ready." if exists else "Workspace is not initialized.",
            "config_path": str(self.config_path),
            "workspace_path": str(store.path),
            "backend": config.workspace.backend,
            "config_exists": True,
            "workspace_exists": exists,
        }

    def state(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {
                "ok": False,
                "ready": False,
                "message": "Config file is missing.",
                "config_path": str(self.config_path),
            }
        config, store = self._store()
        if not store.exists():
            return {
                "ok": False,
                "ready": False,
                "message": "Workspace is not initialized.",
                "config_path": str(self.config_path),
                "workspace_path": str(store.path),
                "backend": config.workspace.backend,
            }
        return self._state(config, store)

    def propose_action(self, payload: ActionProposalRequest) -> dict[str, Any]:
        _, store = self._store(initialize=True)
        action = _validate_action(payload.action_payload())
        appended = store.append_pending_action(action)
        store.append_log(f"API proposed action `{appended.id}`.", actor="api")
        state = self.state()
        self._publish_state("action_proposed", state)
        return {
            "ok": True,
            "message": "Action proposed in the action board; watch must validate before execution.",
            "action": _json_safe(appended),
            "state": state,
        }

    def submit_task(self, payload: SubmitTaskRequest) -> dict[str, Any]:
        task = payload.task.strip()
        if not task:
            raise ApiRequestError("Task cannot be empty.")
        config, store = self._store(initialize=True)
        store.write_task(task, owner="human")
        actions = self._plan_actions(task, store)
        _write_plan(store, task, actions, intent="act" if actions else "task")
        if actions:
            store.append_log(
                f"API submitted task `{task}` as {len(actions)} pending action(s).",
                actor="api",
            )
        else:
            store.append_log(f"API submitted task `{task}` with no action proposal.", actor="api")
        state = self._state(config, store)
        self._publish_state("task_submitted", state)
        return {
            "ok": True,
            "message": (
                "Task recorded and actions proposed; watch must validate before execution."
                if actions
                else "Task recorded. No action proposal was created from current capabilities."
            ),
            "actions": _json_safe(actions),
            "state": state,
        }

    def chat(self, payload: ChatRequest) -> dict[str, Any]:
        message = payload.message.strip()
        if not message:
            raise ApiRequestError("Chat message cannot be empty.")
        config, store = self._store(initialize=True)
        store.append_chat_message("user", message)
        response = self._rule_chat(message, store)
        actions = self._append_planned_actions(response["actions"], store)
        notes = []
        for note in response["memory"]:
            if str(note).strip():
                notes.append(store.append_memory_note(str(note).strip()))
        plan = ChatPlan(
            status="proposed_actions" if actions else "answered",
            intent=response["intent"],
            summary=response["reply"],
            steps=response["steps"],
            actions=actions,
            needs_watch=bool(actions),
        )
        store.write_plan(plan)
        assistant = store.append_chat_message(
            "assistant",
            response["reply"],
            metadata={
                "intent": plan.intent,
                "actions": [action.model_dump(mode="json") for action in actions],
                "needs_watch": plan.needs_watch,
                "executed": 0,
                "surface": "api",
            },
        )
        store.append_log("API chat replied without executing watch.", actor="api")
        state = self._state(config, store)
        self._publish_state("chat", state)
        return {
            "ok": True,
            "mode": "rule_based",
            "reply": assistant.content,
            "actions": _json_safe(actions),
            "memory": _json_safe(notes),
            "plan": plan.model_dump(mode="json"),
            "executed": 0,
            "state": state,
        }

    def search_memory(self, payload: SearchMemoryRequest) -> dict[str, Any]:
        query = payload.query.strip()
        if not query:
            raise ApiRequestError("Search query cannot be empty.")
        _, store = self._store(require_exists=True)
        results = store.query_memory_chunks(
            query,
            limit=max(1, payload.limit),
            tags=payload.tags,
            source_type=payload.source_type,
        )
        return {"ok": True, "query": query, "results": _json_safe(results)}

    def ingest_file(self, payload: IngestFileRequest) -> dict[str, Any]:
        path = payload.path.strip()
        if not path:
            raise ApiRequestError("File path cannot be empty.")
        config, store = self._store(initialize=True)
        try:
            result = ingest_file(
                path,
                store,
                tags=payload.tags,
                importance=payload.importance,
                max_chars_per_chunk=config.memory.retrieval.max_chars_per_chunk,
            )
        except FileIngestionError as exc:
            raise ApiRequestError(
                str(exc),
                status_code=400,
                details={"metadata": exc.metadata},
            ) from exc
        state = self._state(config, store)
        self._publish_state("file_ingested", state)
        return {
            "ok": True,
            "message": "File ingested.",
            "result": _json_safe(result),
            "state": state,
        }

    async def upload_file(
        self,
        upload: Any,
        *,
        tags: str | None = None,
        importance: int = 0,
    ) -> dict[str, Any]:
        filename = _browser_upload_filename(getattr(upload, "filename", None))
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_TEXT_SUFFIXES:
            allowed = ", ".join(sorted(ALLOWED_TEXT_SUFFIXES))
            raise ApiRequestError(
                (
                    f"Unsupported upload type: {suffix or '<none>'}. "
                    f"Supported text suffixes: {allowed}. PDF, OCR, and image ingestion "
                    "are not implemented in this phase."
                ),
                status_code=400,
            )

        config, store = self._store(initialize=True)
        incoming_root = store.uploads_path / ".incoming"
        incoming_root.mkdir(parents=True, exist_ok=True)

        try:
            with tempfile.TemporaryDirectory(
                prefix="browser-upload-",
                dir=incoming_root,
            ) as temp_dir:
                temp_path = Path(temp_dir) / filename
                size_bytes = await _write_browser_upload(upload, temp_path)
                try:
                    result = ingest_file(
                        temp_path,
                        store,
                        tags=_parse_upload_tags(tags),
                        importance=importance,
                        max_chars_per_chunk=config.memory.retrieval.max_chars_per_chunk,
                    )
                except FileIngestionError as exc:
                    raise ApiRequestError(
                        str(exc),
                        status_code=400,
                        details={"metadata": exc.metadata},
                    ) from exc
        except ApiRequestError:
            raise
        except OSError as exc:
            raise ApiRequestError(
                f"Could not store browser upload: {exc}",
                status_code=500,
            ) from exc

        state = self._state(config, store)
        self._publish_state("browser_file_uploaded", state)
        return {
            "ok": True,
            "message": (
                "File uploaded and ingested as untrusted proposal context; "
                "watch must validate any derived action before execution."
            ),
            "filename": filename,
            "size_bytes": size_bytes,
            "result": _json_safe(result),
            "state": state,
        }

    def export_audit(self, payload: ExportAuditRequest) -> dict[str, Any]:
        _, store = self._store(require_exists=True)
        out_dir = None
        if payload.out:
            out_path = Path(payload.out)
            out_dir = out_path if out_path.is_absolute() else self.base_dir / out_path
        result = store.export_human_view(out_dir)
        self._publish_state("audit_exported")
        return {
            "ok": True,
            "message": "Exported audit view.",
            "result": _json_safe(result),
        }

    def _store(
        self,
        *,
        initialize: bool = False,
        require_exists: bool = False,
    ) -> tuple[PhysicalAgentConfig, StateStore]:
        if not self.config_path.exists():
            raise ApiRequestError(
                f"Could not find {self.config_path}. Run `physical-agent init` first.",
                status_code=404,
            )
        config = load_config(self.config_path)
        store = open_state_store(config, base_dir=self.base_dir)
        if initialize:
            store.initialize()
        if require_exists and not store.exists():
            raise ApiRequestError(
                "Workspace is not initialized. Run `physical-agent init` first.",
                status_code=404,
            )
        return config, store

    def _state(self, config: PhysicalAgentConfig, store: StateStore) -> dict[str, Any]:
        actions = store.read_actions()
        return {
            "ok": True,
            "ready": True,
            "message": "Ready.",
            "config_path": str(self.config_path),
            "workspace_path": str(store.path),
            "backend": config.workspace.backend,
            "task": store.read_task(),
            "capabilities": store.read_capabilities(),
            "world": store.read_world(),
            "actions": {
                "pending": _json_safe(actions["pending"]),
                "completed": _json_safe(actions["completed"]),
                "cancelled": _json_safe(actions["cancelled"]),
            },
            "feedback": store.read_feedback(),
            "safety": store.read_safety(),
            "chat": _json_safe(store.read_chat()),
            "plan": _json_safe(store.read_plan()),
            "memory": _json_safe(store.read_memory()),
            "uploads": _json_safe(store.read_uploads()),
            "chunks": _json_safe(store.read_memory_chunks()),
        }

    def _publish_state(self, reason: str, state: dict[str, Any] | None = None) -> None:
        if self.events is None:
            return
        try:
            snapshot = state if state is not None else self.state()
            self.events.publish(
                "state",
                {
                    "reason": reason,
                    "state": summarize_state(snapshot),
                },
            )
        except Exception as exc:
            try:
                self.events.publish("error", error_payload(exc, phase="state_publish"))
            except Exception:
                pass

    def _plan_actions(self, task: str, store: StateStore) -> list[Action]:
        actions = self.planner.plan(
            task=task,
            capabilities=store.read_capabilities(),
            world=store.read_world(),
        )
        return self._append_planned_actions(actions, store)

    def _append_planned_actions(self, actions: list[Action], store: StateStore) -> list[Action]:
        if not actions:
            return []
        renumbered = _renumber_actions(actions, store)
        return [store.append_pending_action(action) for action in renumbered]

    def _rule_chat(self, message: str, store: StateStore) -> dict[str, Any]:
        remember_match = re.search(r"\bremember(?: that)?\s+(.+)", message, re.IGNORECASE)
        if remember_match:
            note = remember_match.group(1).strip()
            return {
                "reply": f"I will remember: {note}",
                "intent": "remember",
                "steps": [],
                "actions": [],
                "memory": [note],
            }

        actions = self.planner.plan(
            task=message,
            capabilities=store.read_capabilities(),
            world=store.read_world(),
        )
        if actions:
            names = ", ".join(f"{action.robot}.{action.capability}" for action in actions)
            return {
                "reply": (
                    f"I proposed {len(actions)} action(s): {names}. "
                    "Watch will validate them before anything touches the physical world."
                ),
                "intent": "act",
                "steps": ["Interpret the message.", "Write proposed actions to the action board."],
                "actions": actions,
                "memory": [],
            }

        text = message.lower().strip()
        if "status" in text or "world" in text or "see" in text:
            latest = store.read_feedback().get("latest", {})
            world = store.read_world()
            reply = world.get("summary") or "No world state has been published yet."
            if latest:
                reply += f" Latest feedback: {latest.get('status')} - {latest.get('message')}"
            return {
                "reply": reply,
                "intent": "inspect",
                "steps": [],
                "actions": [],
                "memory": [],
            }

        if "memory" in text or "remember" in text:
            notes = store.read_memory().get("notes", [])
            notes_text = "; ".join(note.get("content", "") for note in notes[-5:])
            return {
                "reply": notes_text or "I do not have saved memory notes yet.",
                "intent": "inspect",
                "steps": [],
                "actions": [],
                "memory": [],
            }

        return {
            "reply": (
                "I can chat about the workspace, remember short notes, or propose actions like "
                "`look around` and `pick the red block and place it on the tray`."
            ),
            "intent": "chat",
            "steps": [],
            "actions": [],
            "memory": [],
        }


class SafeProposalPlanner:
    """Small request-side planner that only returns pending Action intents."""

    def plan(
        self,
        *,
        task: str,
        capabilities: dict[str, Any],
        world: dict[str, Any],
    ) -> list[Action]:
        text = task.lower()
        robots = capabilities.get("robots", {})
        actions: list[Action] = []

        if any(word in text for word in ("observe", "look", "scan")):
            robot_id = self._choose_robot(robots, ["observe"])
            if robot_id:
                actions.append(
                    Action(
                        id=self._action_id(len(actions) + 1),
                        robot=robot_id,
                        capability="observe",
                        params={},
                        reason="The request asks for an observation.",
                    )
                )

        if re.search(r"\b(move|go)\b", text):
            robot_id = self._choose_robot(robots, ["move_to"])
            if robot_id:
                actions.append(
                    Action(
                        id=self._action_id(len(actions) + 1),
                        robot=robot_id,
                        capability="move_to",
                        params=self._move_params(text, robots[robot_id]),
                        reason="The request asks for movement.",
                    )
                )

        if any(word in text for word in ("pick", "grasp")):
            robot_id = self._choose_robot(robots, ["pick"])
            if robot_id:
                actions.append(
                    Action(
                        id=self._action_id(len(actions) + 1),
                        robot=robot_id,
                        capability="pick",
                        params={"object_id": self._object_id(text, world)},
                        reason="The request asks to pick an object.",
                    )
                )

        if any(word in text for word in ("place", "drop")):
            robot_id = self._choose_robot(robots, ["place"])
            if robot_id:
                depends_on = [actions[-1].id] if actions and actions[-1].capability == "pick" else []
                actions.append(
                    Action(
                        id=self._action_id(len(actions) + 1),
                        robot=robot_id,
                        capability="place",
                        params={"target": self._target_id(text, world)},
                        reason="The request asks to place or drop an object.",
                        depends_on=depends_on,
                    )
                )

        if "open gripper" in text:
            robot_id = self._choose_robot(robots, ["open_gripper"])
            if robot_id:
                actions.append(
                    Action(
                        id=self._action_id(len(actions) + 1),
                        robot=robot_id,
                        capability="open_gripper",
                        params={},
                        reason="The request asks to open the gripper.",
                    )
                )

        if "close gripper" in text:
            robot_id = self._choose_robot(robots, ["close_gripper"])
            if robot_id:
                actions.append(
                    Action(
                        id=self._action_id(len(actions) + 1),
                        robot=robot_id,
                        capability="close_gripper",
                        params={},
                        reason="The request asks to close the gripper.",
                    )
                )

        if any(word in text for word in ("home", "reset")):
            robot_id = self._choose_robot(robots, ["home"])
            if robot_id:
                actions.append(
                    Action(
                        id=self._action_id(len(actions) + 1),
                        robot=robot_id,
                        capability="home",
                        params={},
                        reason="The request asks the robot to return home.",
                    )
                )

        if any(word in text for word in ("stop", "halt")):
            robot_id = self._choose_robot(robots, ["stop"])
            if robot_id:
                actions.append(
                    Action(
                        id=self._action_id(len(actions) + 1),
                        robot=robot_id,
                        capability="stop",
                        params={},
                        reason="The request asks the robot to stop.",
                    )
                )

        return actions

    def _choose_robot(self, robots: dict[str, Any], required: list[str]) -> str | None:
        for robot_id, robot in robots.items():
            names = {capability.get("name") for capability in robot.get("capabilities", [])}
            if all(name in names for name in required):
                return robot_id
        return None

    def _action_id(self, number: int) -> str:
        return f"act_{number:03d}"

    def _object_id(self, text: str, world: dict[str, Any]) -> str:
        objects = world.get("state", {}).get("objects", {})
        if "red block" in text:
            for object_id, item in objects.items():
                if item.get("color") == "red" and item.get("type") == "block":
                    return object_id
            return "red_block"
        match = re.search(r"(?:pick|grasp)\s+(?:the\s+)?([a-z0-9_ -]+?)(?:\s+and|\s+then|$)", text)
        if match:
            candidate = match.group(1).strip().replace(" ", "_").replace("-", "_")
            if candidate:
                return candidate
        return "red_block"

    def _target_id(self, text: str, world: dict[str, Any]) -> str:
        objects = world.get("state", {}).get("objects", {})
        for object_id in objects:
            if object_id.lower() in text:
                return object_id
        if "tray" in text:
            return "tray"
        match = re.search(r"(?:on|in|at|to)\s+(?:the\s+)?([a-z0-9_ -]+?)(?:\.|$)", text)
        if match:
            candidate = match.group(1).strip().replace(" ", "_").replace("-", "_")
            if candidate:
                return candidate
        return "tray"

    def _move_params(self, text: str, robot: dict[str, Any]) -> dict[str, Any]:
        numbers = [float(value) for value in re.findall(r"-?\d+(?:\.\d+)?", text)]
        move_schema = {}
        for capability in robot.get("capabilities", []):
            if capability.get("name") == "move_to":
                move_schema = capability.get("params_schema", {})
                break
        required = move_schema.get("required", ["x", "y", "z"])
        return {
            name: numbers[index] if index < len(numbers) else 0.0
            for index, name in enumerate(required)
        }


def _load_fastapi() -> dict[str, Any]:
    try:
        from fastapi import FastAPI, File, Form, UploadFile
        from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
        from fastapi.staticfiles import StaticFiles
    except ImportError as exc:
        raise MissingServerDependencyError(SERVER_EXTRA_HINT) from exc
    return {
        "FastAPI": FastAPI,
        "File": File,
        "Form": Form,
        "HTMLResponse": HTMLResponse,
        "JSONResponse": JSONResponse,
        "PlainTextResponse": PlainTextResponse,
        "StreamingResponse": StreamingResponse,
        "StaticFiles": StaticFiles,
        "UploadFile": UploadFile,
    }


def _install_frontend_routes(
    app: Any,
    fastapi: dict[str, Any],
    PlainTextResponse: Any,
) -> None:
    dist = _frontend_dist_path()
    index = dist / "index.html"
    assets = dist / "assets"
    HTMLResponse = fastapi["HTMLResponse"]
    StaticFiles = fastapi["StaticFiles"]

    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    def frontend_home() -> Any:
        if index.exists():
            return HTMLResponse(index.read_text(encoding="utf-8"))
        return PlainTextResponse(
            "Physical Agent API is running. GUI build not found; run "
            "`cd frontend && npm install && npm run build` to serve the React dashboard.",
            status_code=200,
        )


def _frontend_dist_path() -> Path:
    candidates = [
        Path.cwd() / "frontend" / "dist",
        Path(__file__).resolve().parents[2] / "frontend" / "dist",
    ]
    for candidate in candidates:
        if (candidate / "index.html").exists():
            return candidate
    return candidates[0]


def _state_event_payload(controller: ApiController, reason: str) -> dict[str, Any]:
    try:
        return {
            "reason": reason,
            "state": summarize_state(controller.state()),
        }
    except Exception as exc:
        return {
            "reason": reason,
            "state": {
                "ok": False,
                "ready": False,
                "message": f"State snapshot failed: {type(exc).__name__}: {exc}",
            },
        }


def _validate_action(payload: dict[str, Any]) -> Action:
    try:
        return Action.model_validate(payload)
    except Exception as exc:
        raise ApiRequestError(f"Invalid action proposal: {exc}") from exc


def _write_plan(store: StateStore, summary: str, actions: list[Action], *, intent: str) -> None:
    store.write_plan(
        ChatPlan(
            status="proposed_actions" if actions else "answered",
            intent=intent,
            summary=summary,
            steps=["Record task.", "Write proposed actions to the action board."] if actions else ["Record task."],
            actions=actions,
            needs_watch=bool(actions),
        )
    )


def _renumber_actions(actions: list[Action], store: StateStore) -> list[Action]:
    start = _max_action_number(_known_action_ids(store)) + 1
    old_to_new: dict[str, str] = {}
    items: list[dict[str, Any]] = []
    for offset, action in enumerate(actions):
        data = action.model_dump(mode="json")
        old_id = data["id"]
        new_id = f"act_{start + offset:03d}"
        old_to_new[old_id] = new_id
        data["id"] = new_id
        items.append(data)

    result = []
    for data in items:
        data["depends_on"] = [
            old_to_new.get(str(dependency), str(dependency))
            for dependency in data.get("depends_on", [])
        ]
        result.append(Action.model_validate(data))
    return result


async def _write_browser_upload(upload: Any, destination: Path) -> int:
    total = 0
    with destination.open("wb") as handle:
        while True:
            chunk = await upload.read(UPLOAD_READ_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > BROWSER_UPLOAD_MAX_BYTES:
                limit_mb = BROWSER_UPLOAD_MAX_BYTES // (1024 * 1024)
                raise ApiRequestError(
                    f"Uploaded file exceeds the {limit_mb}MB limit.",
                    status_code=413,
                    details={
                        "max_bytes": BROWSER_UPLOAD_MAX_BYTES,
                        "received_bytes": total,
                    },
                )
            handle.write(chunk)
    return total


def _browser_upload_filename(filename: str | None) -> str:
    safe_name = sanitize_filename(filename or "upload.txt")
    if not safe_name:
        raise ApiRequestError("Upload filename cannot be empty.")
    return safe_name


def _parse_upload_tags(tags: str | None) -> list[str]:
    if not tags:
        return []
    return [
        item.strip()
        for item in re.split(r"[,;\n]+", tags)
        if item.strip()
    ]


def _known_action_ids(store: StateStore) -> set[str]:
    board = store.read_actions()
    ids = {
        action.id
        for action in board["pending"] + board["completed"] + board["cancelled"]
    }
    for item in store.read_feedback().get("history", []):
        action_id = item.get("action_id")
        if action_id:
            ids.add(str(action_id))
    return ids


def _max_action_number(action_ids: set[str]) -> int:
    maximum = 0
    for action_id in action_ids:
        if action_id.startswith("act_"):
            try:
                maximum = max(maximum, int(action_id.removeprefix("act_")))
            except ValueError:
                continue
    return maximum


def _json_safe(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return value
