from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
import re
import tempfile
import threading
from typing import Any, Callable, Iterator, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from physical_agent.application.plan_compiler import task_graph_steps
from physical_agent.application.output_projection import project_chat_plan
from physical_agent.application.proposals import ProposalService
from physical_agent.application.ports import PlannerPort
from physical_agent.agent.planner_factory import create_planner
from physical_agent.api.watch_service import (
    ApiEventBroker,
    ApiWatchService,
    error_payload,
    format_sse_event,
    summarize_state,
)
from physical_agent.config import (
    DEFAULT_CONFIG_NAME,
    PhysicalAgentConfig,
    load_config,
    write_default_config,
)
from physical_agent.ingest.files import (
    ALLOWED_TEXT_SUFFIXES,
    FileIngestionError,
    ingest_file,
    sanitize_filename,
)
from physical_agent.llm import (
    LLMSettingsError,
    OpenAICompatibleClient,
    OpenAICompatibleSettings,
    StructuredOutputError,
    llm_settings_path,
    public_llm_settings_summary,
    resolve_llm_settings_values,
    write_llm_settings_file,
)
from physical_agent.protocol.agent_output import AgentOutput
from physical_agent.protocol.schemas import Action, ChatPlan
from physical_agent.state import ActiveRuntimeLeaseError, StateStore, open_state_store
from physical_agent.state.check import run_state_check, state_check_ok


BROWSER_UPLOAD_MAX_BYTES = 5 * 1024 * 1024
UPLOAD_READ_CHUNK_BYTES = 1024 * 1024
EXECUTOR_EVENT_INTERVAL_S = 5.0

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
    metadata: dict[str, Any] = Field(default_factory=dict)

    def action_payload(self) -> dict[str, Any]:
        if self.action is not None:
            return dict(self.action)
        data = self.model_dump(exclude_none=True, exclude={"action"})
        return data


class ActionApprovalRequest(BaseModel):
    actor: str | None = None
    reason: str | None = None

    def normalized_actor(self, default: str = "gui") -> str:
        return (self.actor or default).strip() or default

    def normalized_reason(self) -> str | None:
        value = (self.reason or "").strip()
        return value or None


class SubmitTaskRequest(BaseModel):
    task: str


class ChatRequest(BaseModel):
    message: str
    planner: str | None = None
    request_id: str | None = None
    stream_id: str | None = None


class ActionProposalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    message: str
    agent_output: AgentOutput
    state: dict[str, Any]


class SubmitTaskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    message: str
    agent_output: AgentOutput
    refusal_reason: str | None = None
    proposal_status: str
    proposal_id: str | None = None
    state: dict[str, Any]


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    mode: str
    reply: str
    agent_output: AgentOutput | None = None
    memory: list[Any] = Field(default_factory=list)
    plan: ChatPlan | None = None
    refusal_reason: str | None = None
    state: dict[str, Any]


class ActionMutationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    message: str
    action: Action
    changed: bool | None = None
    state: dict[str, Any]


class LLMSettingsRequest(BaseModel):
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    api_mode: str | None = None
    reasoning_enabled: bool | None = None
    reasoning_effort: str | None = None
    reasoning_summary: str | None = None
    reasoning_extra_body: dict[str, Any] | None = None
    clear_api_key: bool = False


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


class WorkspaceResetRequest(BaseModel):
    confirm: bool = False


class IntegrateRequest(BaseModel):
    source: str
    name: str | None = None
    output: str | None = None
    llm: bool = False
    model: str | None = None


class RegisterRobotRequest(BaseModel):
    robot_id: str
    driver: str
    execution_mode: Literal["simulation", "hardware"] = "hardware"
    config: dict[str, Any] = Field(default_factory=dict)


@dataclass
class ChatStreamState:
    stream_id: str
    request_id: str
    abort_event: threading.Event
    _transport_closer: Callable[[], None] | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _transport_lock: threading.Lock = field(
        default_factory=threading.Lock,
        init=False,
        repr=False,
    )

    def observe_transport(self, closer: Callable[[], None] | None) -> None:
        close_now: Callable[[], None] | None = None
        with self._transport_lock:
            if closer is None:
                self._transport_closer = None
            elif self.abort_event.is_set():
                close_now = closer
            else:
                self._transport_closer = closer
        _best_effort_close(close_now)

    def abort(self) -> None:
        self.abort_event.set()
        with self._transport_lock:
            closer = self._transport_closer
            self._transport_closer = None
        _best_effort_close(closer)


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
    Request = fastapi["Request"]
    StreamingResponse = fastapi["StreamingResponse"]
    UploadFile = fastapi["UploadFile"]

    # FastAPI resolves postponed annotations from module globals.
    globals()["Request"] = Request
    globals()["UploadFile"] = UploadFile

    events = ApiEventBroker()
    controller = ApiController(
        config_path,
        events=events,
        embedded_watch_enabled=enable_watch,
    )

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
            controller.bind_watch_service(service)
            await service.start()
        try:
            yield
        finally:
            service = getattr(app.state, "watch_service", None)
            if service is not None:
                await service.stop()
                controller.bind_watch_service(None)

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

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, exc: Exception) -> Any:
        # Unexpected exceptions can contain provider output, credentials, or
        # local paths.  Detailed diagnostics stay in server-side logs/traces.
        return JSONResponse(
            status_code=500,
            content={"ok": False, "message": "Internal server error."},
        )

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return controller.health()

    @app.get("/api/state")
    def state() -> dict[str, Any]:
        return controller.state()

    @app.post("/api/project/initialize")
    def initialize_project() -> dict[str, Any]:
        try:
            return controller.initialize_project()
        except ApiRequestError as exc:
            return handle_error(exc)

    @app.get("/api/state-check")
    def state_check() -> dict[str, Any]:
        try:
            return controller.state_check()
        except ApiRequestError as exc:
            return handle_error(exc)

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
                            "executor": controller.executor_status(),
                        },
                    )
                )
                if should_stop():
                    return
                yield emit(events.make_event("state", _state_event_payload(controller, "connect")))
                if should_stop():
                    return
                while True:
                    event = subscription.get(timeout_s=EXECUTOR_EVENT_INTERVAL_S)
                    if event is None:
                        yield emit(
                            events.make_event(
                                "executor",
                                {
                                    "executor": controller.executor_status()
                                },
                            )
                        )
                        if should_stop():
                            return
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

    @app.post("/api/actions/propose", response_model=ActionProposalResponse)
    def propose_action(payload: ActionProposalRequest) -> dict[str, Any]:
        try:
            return controller.propose_action(payload)
        except ApiRequestError as exc:
            return handle_error(exc)

    @app.post(
        "/api/actions/{action_id}/approve",
        response_model=ActionMutationResponse,
        response_model_exclude_none=True,
    )
    def approve_action(action_id: str, payload: ActionApprovalRequest | None = None) -> dict[str, Any]:
        try:
            return controller.approve_action(action_id, payload or ActionApprovalRequest())
        except ApiRequestError as exc:
            return handle_error(exc)

    @app.post(
        "/api/actions/{action_id}/reject",
        response_model=ActionMutationResponse,
        response_model_exclude_none=True,
    )
    def reject_action(action_id: str, payload: ActionApprovalRequest | None = None) -> dict[str, Any]:
        try:
            return controller.reject_action(action_id, payload or ActionApprovalRequest())
        except ApiRequestError as exc:
            return handle_error(exc)

    @app.post("/api/tasks/submit", response_model=SubmitTaskResponse)
    def submit_task(payload: SubmitTaskRequest) -> dict[str, Any]:
        try:
            return controller.submit_task(payload)
        except ApiRequestError as exc:
            return handle_error(exc)

    @app.post(
        "/api/chat",
        response_model=ChatResponse,
        response_model_exclude_none=True,
    )
    def chat(payload: ChatRequest) -> dict[str, Any]:
        try:
            return controller.chat(payload)
        except ApiRequestError as exc:
            return handle_error(exc)

    @app.post("/api/chat/reset")
    def reset_chat() -> dict[str, Any]:
        try:
            return controller.reset_chat()
        except ApiRequestError as exc:
            return handle_error(exc)

    @app.post("/api/chat/stream")
    async def chat_stream(payload: ChatRequest, request: Request) -> Any:
        try:
            stream_state = controller.register_chat_stream(payload)
        except ApiRequestError as exc:
            return handle_error(exc)

        async def stream() -> Any:
            yield format_sse_event(
                events.make_event(
                    "start",
                    {
                        "stream_id": stream_state.stream_id,
                        "request_id": stream_state.request_id,
                    },
                )
            )
            iterator = controller.chat_stream(payload, stream_state=stream_state)
            try:
                while True:
                    if await request.is_disconnected():
                        controller.abort_chat_stream(
                            stream_state.stream_id,
                            reason="client disconnected",
                        )
                        controller.log_chat_stream_disconnect(stream_state.stream_id)
                        _close_iterator(iterator)
                        return
                    item = await asyncio.to_thread(_next_stream_item, iterator)
                    if item is None:
                        return
                    yield format_sse_event(events.make_event(item["type"], item["payload"]))
                    await asyncio.sleep(0)
            except Exception as exc:  # noqa: BLE001 - stream errors must become SSE events.
                error_payload_data = {
                    "stream_id": stream_state.stream_id,
                    "request_id": stream_state.request_id,
                    "message": _sanitize_api_message(
                        str(exc),
                        controller.safe_resolved_llm_settings_values(),
                    ),
                }
                yield format_sse_event(events.make_event("error", error_payload_data))
            finally:
                controller.unregister_chat_stream(stream_state.stream_id)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/api/chat/abort/{stream_id}")
    def abort_chat(stream_id: str) -> dict[str, Any]:
        aborted = controller.abort_chat_stream(stream_id, reason="abort endpoint")
        return {
            "ok": True,
            "stream_id": stream_id,
            "aborted": aborted,
        }

    @app.get("/api/settings/llm")
    def get_llm_settings() -> dict[str, Any]:
        try:
            return controller.get_llm_settings()
        except ApiRequestError as exc:
            return handle_error(exc)

    @app.post("/api/settings/llm")
    def update_llm_settings(payload: LLMSettingsRequest) -> dict[str, Any]:
        try:
            return controller.update_llm_settings(payload)
        except ApiRequestError as exc:
            return handle_error(exc)

    @app.post("/api/settings/llm/test")
    def test_llm_settings() -> dict[str, Any]:
        try:
            return controller.test_llm_settings()
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

    @app.post("/api/workspace/reset")
    def workspace_reset(payload: WorkspaceResetRequest) -> dict[str, Any]:
        try:
            return controller.reset_workspace(payload)
        except ApiRequestError as exc:
            return handle_error(exc)

    @app.post("/api/integrate")
    def integrate(payload: IntegrateRequest) -> dict[str, Any]:
        try:
            return controller.integrate_hardware(payload)
        except ApiRequestError as exc:
            return handle_error(exc)

    @app.get("/api/config")
    def get_config() -> dict[str, Any]:
        try:
            return controller.get_config()
        except ApiRequestError as exc:
            return handle_error(exc)

    @app.post("/api/config/robots")
    def register_robot(payload: RegisterRobotRequest) -> dict[str, Any]:
        try:
            return controller.register_robot(payload)
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
        planner: PlannerPort | None = None,
        embedded_watch_enabled: bool = False,
    ):
        self.config_path = Path(config_path).resolve()
        self.base_dir = self.config_path.parent
        self.events = events
        self._planner_override = planner
        self._embedded_watch_enabled = bool(embedded_watch_enabled)
        self._watch_service: ApiWatchService | None = None
        self._initialize_lock = threading.Lock()
        self._chat_streams: dict[str, ChatStreamState] = {}
        self._chat_stream_lock = threading.Lock()

    def bind_watch_service(self, service: ApiWatchService | None) -> None:
        self._watch_service = service

    def health(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return self._with_executor(
                {
                    "ok": False,
                    "ready": False,
                    "message": "Config file is missing.",
                    "config_path": str(self.config_path),
                    "config_exists": False,
                    "workspace_exists": False,
                }
            )
        try:
            config, store = self._store()
        except Exception as exc:
            return self._with_executor(
                {
                    "ok": False,
                    "ready": False,
                    "message": str(exc),
                    "config_path": str(self.config_path),
                    "config_exists": True,
                    "workspace_exists": False,
                }
            )
        exists = store.exists()
        return self._with_executor(
            {
                "ok": True,
                "ready": exists,
                "message": "Ready." if exists else "Workspace is not initialized.",
                "config_path": str(self.config_path),
                "workspace_path": str(store.path),
                "backend": config.workspace.backend,
                "config_exists": True,
                "workspace_exists": exists,
            }
        )

    def state(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return self._with_executor(
                {
                    "ok": False,
                    "ready": False,
                    "message": "Config file is missing.",
                    "config_path": str(self.config_path),
                }
            )
        try:
            config, store = self._store()
        except Exception as exc:
            return self._with_executor(
                {
                    "ok": False,
                    "ready": False,
                    "message": str(exc),
                    "config_path": str(self.config_path),
                }
            )
        if not store.exists():
            return self._with_executor(
                {
                    "ok": False,
                    "ready": False,
                    "message": "Workspace is not initialized.",
                    "config_path": str(self.config_path),
                    "workspace_path": str(store.path),
                    "backend": config.workspace.backend,
                }
            )
        return self._state(config, store)

    def initialize_project(self) -> dict[str, Any]:
        with self._initialize_lock:
            return self._initialize_project_once()

    def _initialize_project_once(self) -> dict[str, Any]:
        config_created = not self.config_path.exists()
        if config_created:
            write_default_config(self.config_path, overwrite=False)
        try:
            config = load_config(self.config_path)
            store = open_state_store(config, base_dir=self.base_dir)
        except Exception as exc:
            raise ApiRequestError(
                f"Existing config is invalid; nothing was overwritten: {exc}",
                status_code=400,
            ) from exc

        workspace_created = not store.exists()
        try:
            store.initialize(overwrite=False)
        except ActiveRuntimeLeaseError as exc:
            raise ApiRequestError(str(exc), status_code=409) from exc
        if config_created or workspace_created:
            store.append_log(
                "API initialized the project without replacing existing config or state.",
                actor="api",
            )
        state = self._state(config, store)
        self._publish_state("project_initialized", state)
        return {
            "ok": True,
            "message": (
                "Project initialized."
                if config_created or workspace_created
                else "Project is already initialized."
            ),
            "config_created": config_created,
            "workspace_created": workspace_created,
            "state": state,
        }

    def executor_status(self) -> dict[str, Any]:
        initialized, lease, projection_error = self._executor_storage_snapshot()
        service_status = (
            self._watch_service.status()
            if self._watch_service is not None
            else {
                "phase": "stopped",
                "task_running": False,
                "owner": None,
                "last_error": None,
            }
        )
        lease_active = bool(lease and lease.get("active"))
        local_owner = service_status.get("owner")
        lease_owner = lease.get("owner") if lease else None

        if lease_active:
            mode = (
                "embedded"
                if self._embedded_watch_enabled
                and local_owner is not None
                and local_owner == lease_owner
                else "external"
            )
        elif self._embedded_watch_enabled:
            mode = "embedded" if initialized else "waiting_for_init"
        else:
            mode = "none"

        if mode == "external":
            status = "active"
        elif mode == "waiting_for_init":
            service_phase = str(service_status.get("phase") or "waiting_for_init")
            status = (
                service_phase
                if service_phase in {"invalid_config", "degraded"}
                else "waiting_for_init"
            )
        elif mode == "embedded":
            status = str(service_status.get("phase") or "stopped")
            if initialized and status == "waiting_for_init":
                status = "starting"
        else:
            status = "stopped"

        return {
            "mode": mode,
            "status": status,
            "embedded_enabled": self._embedded_watch_enabled,
            "lease": _json_safe(lease),
            "last_error": _json_safe(
                service_status.get("last_error") or projection_error
            ),
        }

    def state_check(self) -> dict[str, Any]:
        if not self.config_path.exists():
            raise ApiRequestError(
                f"Could not find {self.config_path}. Run `physical-agent init` first.",
                status_code=404,
            )
        config = load_config(self.config_path)
        result = run_state_check(config, base_dir=self.base_dir)
        ok = state_check_ok(result)
        return {
            "ok": ok,
            "ready": bool(result["workspace_initialized"]),
            "message": "State backend is ready." if ok else "State backend needs attention.",
            **_json_safe(result),
        }

    def propose_action(self, payload: ActionProposalRequest) -> dict[str, Any]:
        _, store = self._store(initialize=True)
        action_payload = payload.action_payload()
        client_metadata = action_payload.get("metadata")
        client_source = (
            client_metadata.get("source")
            if isinstance(client_metadata, dict)
            else None
        )
        user_message = _metadata_text(client_metadata, "user_message")
        draft_reason = _metadata_text(client_metadata, "draft_reason")
        source = "chat_draft" if client_source == "chat_draft" else "manual"
        action = _validate_action(action_payload)
        try:
            proposal = ProposalService(store).propose_action_result(
                action,
                source=source,
                proposed_by="api",
                user_message=user_message,
                draft_reason=draft_reason,
            )
        except ValueError as exc:
            raise ApiRequestError(
                f"Invalid action proposal: {exc}",
                status_code=422,
            ) from exc
        agent_output = proposal.agent_output
        appended = agent_output.actions[0]
        _write_plan(
            store,
            appended.reason or f"Propose {appended.id}",
            intent="act",
            agent_output=agent_output,
        )
        store.append_log(f"API proposed action `{appended.id}`.", actor="api")
        state = self.state()
        self._publish_state("action_proposed", state)
        return {
            "ok": True,
            "message": proposal.message,
            "agent_output": agent_output.model_dump(mode="json", by_alias=True),
            "state": state,
        }

    def approve_action(
        self,
        action_id: str,
        payload: ActionApprovalRequest,
    ) -> dict[str, Any]:
        _, store = self._store(require_exists=True)
        try:
            action, changed = store.approve_action(
                action_id,
                actor=payload.normalized_actor(),
                reason=payload.normalized_reason(),
            )
        except KeyError as exc:
            raise ApiRequestError(
                f"Action not found: {action_id}",
                status_code=404,
            ) from exc
        except ValueError as exc:
            raise ApiRequestError(str(exc), status_code=409) from exc
        if changed:
            store.append_log(
                f"API approved action `{action.id}` for execution.",
                actor="api",
            )
        state = self.state()
        self._publish_state("action_approved", state)
        return {
            "ok": True,
            "message": (
                "Action approved for watch execution."
                if changed
                else "Action approval is already current."
            ),
            "action": _json_safe(action),
            "changed": changed,
            "state": state,
        }

    def reject_action(
        self,
        action_id: str,
        payload: ActionApprovalRequest,
    ) -> dict[str, Any]:
        _, store = self._store(require_exists=True)
        reason = payload.normalized_reason()
        try:
            action = store.reject_action(
                action_id,
                actor=payload.normalized_actor(),
                reason=reason,
            )
        except KeyError as exc:
            raise ApiRequestError(
                f"Action not found: {action_id}",
                status_code=404,
            ) from exc
        except ValueError as exc:
            raise ApiRequestError(str(exc), status_code=409) from exc
        store.append_log(
            f"API rejected action `{action.id}`: "
            f"{reason or 'Rejected by human reviewer.'}",
            actor="api",
        )
        state = self.state()
        self._publish_state("action_rejected", state)
        return {
            "ok": True,
            "message": "Action rejected and moved to cancelled.",
            "action": _json_safe(action),
            "state": state,
        }

    def submit_task(self, payload: SubmitTaskRequest) -> dict[str, Any]:
        task = payload.task.strip()
        if not task:
            raise ApiRequestError("Task cannot be empty.")
        config, store = self._store(initialize=True)
        try:
            proposal = ProposalService(
                store,
                planner_factory=lambda: self._task_planner(config),
            ).submit_task(
                task,
                proposed_by="api",
            )
        except StructuredOutputError as exc:
            raise _structured_output_api_error(exc) from exc
        except ValueError as exc:
            raise ApiRequestError(
                f"Task produced an invalid action proposal: {exc}",
                status_code=422,
            ) from exc
        agent_output = proposal.agent_output
        actions = agent_output.actions
        _write_plan(
            store,
            task,
            intent="act" if actions else "task",
            agent_output=agent_output,
        )
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
            "ok": proposal.ok,
            "message": proposal.message,
            "agent_output": agent_output.model_dump(
                mode="json", by_alias=True
            ),
            "refusal_reason": proposal.refusal_reason,
            "proposal_status": proposal.status,
            "proposal_id": proposal.correlation.proposal_id,
            "state": state,
        }

    def chat(self, payload: ChatRequest) -> dict[str, Any]:
        message = payload.message.strip()
        if not message:
            raise ApiRequestError("Chat message cannot be empty.")
        self._store(initialize=True)
        runtime = _new_chat_runtime(
            self.config_path,
            planner_name=_api_chat_planner(payload.planner),
            enable_code_skills=False,
            enable_hardware_integration=False,
        )
        try:
            response = runtime.respond(message)
        except StructuredOutputError as exc:
            raise _structured_output_api_error(exc) from exc
        config, store = self._store(require_exists=True)
        store.append_log("API chat replied without executing watch.", actor="api")
        state = self._state(config, store)
        self._publish_state("chat", state)
        return {
            "ok": True,
            "mode": response.get("mode", "rule_based"),
            "reply": response.get("reply", ""),
            "agent_output": _json_safe(response.get("agent_output")),
            "memory": _json_safe(response.get("memory", [])),
            "plan": _json_safe(response.get("plan")),
            "refusal_reason": response.get("refusal_reason"),
            "state": state,
        }

    def reset_chat(self) -> dict[str, Any]:
        config, store = self._store(initialize=True)
        store.write_chat([], running_summary="", compact=False)
        store.append_log("API reset chat history.", actor="api")
        state = self._state(config, store)
        self._publish_state("chat_reset", state)
        return {
            "ok": True,
            "message": "Chat history cleared.",
            "state": state,
        }

    def register_chat_stream(self, payload: ChatRequest) -> ChatStreamState:
        stream_id = (payload.stream_id or "").strip() or f"chat_{uuid4().hex}"
        request_id = (payload.request_id or "").strip() or stream_id
        stream_state = ChatStreamState(
            stream_id=stream_id,
            request_id=request_id,
            abort_event=threading.Event(),
        )
        with self._chat_stream_lock:
            if stream_id in self._chat_streams:
                raise ApiRequestError(
                    f"Chat stream already exists: {stream_id}",
                    status_code=409,
                )
            self._chat_streams[stream_id] = stream_state
        return stream_state

    def unregister_chat_stream(self, stream_id: str) -> None:
        with self._chat_stream_lock:
            self._chat_streams.pop(stream_id, None)

    def abort_chat_stream(self, stream_id: str, *, reason: str = "abort requested") -> bool:
        with self._chat_stream_lock:
            stream_state = self._chat_streams.get(stream_id)
        if stream_state is None:
            return False
        stream_state.abort()
        try:
            _, store = self._store(require_exists=True)
            store.append_log(f"API chat stream `{stream_id}` abort requested: {reason}.", actor="api")
        except Exception:
            pass
        return True

    def log_chat_stream_disconnect(self, stream_id: str) -> None:
        try:
            _, store = self._store(require_exists=True)
            store.append_log(f"API chat stream `{stream_id}` stopped after client disconnect.", actor="api")
        except Exception:
            pass

    def chat_stream(
        self,
        payload: ChatRequest,
        *,
        stream_state: ChatStreamState,
    ) -> Iterator[dict[str, Any]]:
        message = payload.message.strip()
        if not message:
            raise ApiRequestError("Chat message cannot be empty.")
        self._store(initialize=True)
        runtime = _new_chat_runtime(
            self.config_path,
            planner_name=_api_chat_planner(payload.planner),
            enable_code_skills=False,
            enable_hardware_integration=False,
        )
        runtime_stream = runtime.respond_stream(
            message,
            cancel_check=stream_state.abort_event.is_set,
            transport_observer=stream_state.observe_transport,
        )
        try:
            while True:
                if stream_state.abort_event.is_set():
                    close = getattr(runtime_stream, "close", None)
                    if callable(close):
                        close()
                    config, store = self._store(require_exists=True)
                    state = self._state(config, store)
                    self._publish_state("chat_stream_aborted", state)
                    yield {
                        "type": "aborted",
                        "payload": {
                            "stream_id": stream_state.stream_id,
                            "request_id": stream_state.request_id,
                            "state": _json_safe(state),
                        },
                    }
                    return
                try:
                    item = next(runtime_stream)
                except StopIteration:
                    return
                event_type = str(item.get("type") or "delta")
                payload_data = {
                    "stream_id": stream_state.stream_id,
                    "request_id": stream_state.request_id,
                }
                if event_type in {"delta", "thought"}:
                    payload_data["delta"] = str(item.get("delta") or "")
                elif event_type == "done":
                    config, store = self._store(require_exists=True)
                    store.append_log("API chat stream completed without executing watch.", actor="api")
                    state = self._state(config, store)
                    self._publish_state("chat_stream", state)
                    agent_output = _json_safe(item.get("agent_output"))
                    payload_data.update(
                        {
                            "reply": item.get("reply", ""),
                            "mode": item.get("mode", "rule_based"),
                            "agent_output": agent_output,
                            "plan": _json_safe(item.get("plan")),
                            "state": _json_safe(state),
                        }
                    )
                elif event_type in {"aborted", "error"}:
                    config, store = self._store(require_exists=True)
                    store.append_log(f"API chat stream {event_type} without executing watch.", actor="api")
                    state = self._state(config, store)
                    self._publish_state(f"chat_stream_{event_type}", state)
                    payload_data.update(
                        {
                            "reply": item.get("reply", ""),
                            "mode": item.get("mode", "rule_based"),
                            "message": _sanitize_api_message(
                                str(item.get("message", "")),
                                self.safe_resolved_llm_settings_values(),
                            ),
                            "state": _json_safe(state),
                        }
                    )
                    if event_type == "error":
                        for key in ("code", "reason", "attempts"):
                            if item.get(key) is not None:
                                payload_data[key] = _json_safe(item[key])
                else:
                    payload_data.update(_json_safe(item))
                yield {"type": event_type, "payload": payload_data}
        finally:
            close = getattr(runtime_stream, "close", None)
            if callable(close):
                close()
            stream_state.observe_transport(None)

    def safe_resolved_llm_settings_values(self) -> dict[str, str]:
        try:
            return self._resolved_llm_settings_values()
        except Exception:
            return {}

    def get_llm_settings(self) -> dict[str, Any]:
        values = self._resolved_llm_settings_values()
        summary = public_llm_settings_summary(
            values,
            settings_path=self._llm_settings_path(),
        )
        return {
            "ok": True,
            **summary,
            "settings": summary,
        }

    def update_llm_settings(self, payload: LLMSettingsRequest) -> dict[str, Any]:
        settings_path = self._llm_settings_path()
        data = payload.model_dump(exclude_unset=True)
        if payload.clear_api_key and "api_key" not in data:
            data["api_key"] = ""
        try:
            written = write_llm_settings_file(
                settings_path,
                data,
                preserve_existing_api_key=not payload.clear_api_key,
            )
        except LLMSettingsError as exc:
            raise ApiRequestError(str(exc), status_code=400) from exc
        summary = public_llm_settings_summary(
            written,
            settings_path=settings_path,
        )
        return {
            "ok": True,
            "message": "LLM settings saved.",
            **summary,
            "settings": summary,
        }

    def test_llm_settings(self) -> dict[str, Any]:
        settings_path = self._llm_settings_path()
        try:
            settings = OpenAICompatibleSettings.from_env(
                env_file=self.base_dir / ".env",
                workspace_path=settings_path.parent,
            )
            result = OpenAICompatibleClient(settings).test_connection()
        except Exception as exc:
            message = _sanitize_api_message(str(exc), self._resolved_llm_settings_values())
            summary = public_llm_settings_summary(
                self._resolved_llm_settings_values(),
                settings_path=settings_path,
            )
            return {
                "ok": False,
                "message": message,
                **summary,
                "settings": summary,
            }
        summary = public_llm_settings_summary(
            {
                "base_url": settings.base_url,
                "model": settings.model,
                "api_mode": settings.api_mode,
                "reasoning_enabled": settings.reasoning_enabled,
                "reasoning_effort": settings.reasoning_effort,
                "reasoning_summary": settings.reasoning_summary,
                "reasoning_extra_body": settings.reasoning_extra_body,
                "api_key": settings.api_key,
            },
            settings_path=settings_path,
        )
        return {
            "ok": True,
            "message": "LLM connection test passed.",
            "result": {
                key: value
                for key, value in result.items()
                if key != "content"
            },
            **summary,
            "settings": summary,
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
            "backend": result.get("backend"),
            "workspace_path": result.get("workspace_path"),
            "out_dir": result.get("out_dir"),
            "manifest": result.get("manifest"),
            "result": _json_safe(result),
        }

    def reset_workspace(self, payload: WorkspaceResetRequest) -> dict[str, Any]:
        if not payload.confirm:
            raise ApiRequestError(
                "Workspace reset requires explicit confirmation. "
                "Send {\"confirm\": true} to clear world, actions, memory, and chat.",
                status_code=400,
            )
        config, store = self._store()
        try:
            store.initialize(overwrite=True)
        except ActiveRuntimeLeaseError as exc:
            raise ApiRequestError(str(exc), status_code=409) from exc
        store.append_log(
            "API reset the workspace (full state re-init; config file untouched).",
            actor="api",
        )
        state = self.state()
        self._publish_state("workspace_reset", state)
        return {
            "ok": True,
            "message": (
                "Workspace has been reset: world, actions, memory, chat, and uploads "
                "are cleared; SAFETY hard Rules are restored to defaults while "
                "Agent Guidance is preserved. "
                "physical-agent.yaml is untouched. "
                "Capabilities will be republished the next time watch runs."
            ),
            "workspace_path": str(store.path),
            "backend": config.workspace.backend,
            "state": state,
        }

    def integrate_hardware(self, payload: IntegrateRequest) -> dict[str, Any]:
        source = payload.source.strip()
        if not source:
            raise ApiRequestError("Integration source cannot be empty.")
        _, store = self._store(initialize=True)
        from physical_agent.agent.driver_coder import DriverCodingAgent
        from physical_agent.agent.onboarding import HardwareIntegrationAssistant

        try:
            if payload.llm:
                coding_result = DriverCodingAgent(
                    source,
                    output_dir=payload.output or None,
                    name=payload.name or None,
                    base_dir=self.base_dir,
                    model=payload.model or None,
                ).generate()
                message = (
                    f"Generated LLM driver draft at {coding_result.output_path}."
                    if coding_result.llm_used
                    else (
                        f"Generated safe scaffold at {coding_result.output_path}; "
                        "LLM coding did not validate."
                    )
                )
                result_payload = coding_result.model_dump(mode="json")
            else:
                integration_result = HardwareIntegrationAssistant(
                    source,
                    output_dir=payload.output or None,
                    name=payload.name or None,
                    base_dir=self.base_dir,
                ).generate()
                message = f"Generated driver scaffold at {integration_result.output_path}."
                result_payload = integration_result.model_dump(mode="json")
        except ApiRequestError:
            raise
        except Exception as exc:
            raise ApiRequestError(str(exc), status_code=400) from exc
        store.append_log(
            f"API generated a driver {'draft' if payload.llm else 'scaffold'} "
            f"from `{source}`. Watch must load and validate it before execution.",
            actor="api",
        )
        state = self.state()
        self._publish_state("hardware_integrated", state)
        return {
            "ok": True,
            "message": message,
            "result": _json_safe(result_payload),
            "state": state,
        }

    def get_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            raise ApiRequestError(
                f"Could not find {self.config_path}. Run `physical-agent init` first.",
                status_code=404,
            )
        try:
            config = load_config(self.config_path)
        except Exception as exc:
            raise ApiRequestError(f"Config file is invalid: {exc}", status_code=400) from exc
        return {
            "ok": True,
            "message": "Effective configuration as watch would load it. Read-only.",
            "config_path": str(self.config_path),
            "config": _json_safe(config.model_dump(mode="json")),
        }

    def register_robot(self, payload: RegisterRobotRequest) -> dict[str, Any]:
        robot_id = payload.robot_id.strip()
        driver = payload.driver.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", robot_id or ""):
            raise ApiRequestError(
                "robot_id must start with a letter or underscore and contain only "
                "letters, digits, '_' or '-'."
            )
        if not driver:
            raise ApiRequestError("driver cannot be empty.")
        if not self.config_path.exists():
            raise ApiRequestError(
                f"Could not find {self.config_path}. Run `physical-agent init` first.",
                status_code=404,
            )
        import yaml as _yaml

        try:
            data = _yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            raise ApiRequestError(f"Config file is invalid YAML: {exc}", status_code=400) from exc
        if not isinstance(data, dict):
            raise ApiRequestError(
                "Config file is invalid: top level must be a mapping.", status_code=400
            )
        robots = data.setdefault("robots", {})
        if not isinstance(robots, dict):
            raise ApiRequestError(
                "Config file is invalid: `robots` must be a mapping.", status_code=400
            )
        if robot_id in robots:
            raise ApiRequestError(
                f"Robot `{robot_id}` already exists in {self.config_path.name}. "
                "Editing existing robots from the GUI is not supported; edit the file manually.",
                status_code=409,
            )
        robots[robot_id] = {
            "driver": driver,
            "execution_mode": payload.execution_mode,
            "config": dict(payload.config),
        }
        try:
            PhysicalAgentConfig.model_validate(data)
        except Exception as exc:
            raise ApiRequestError(
                f"New robot entry failed config validation; nothing was written: {exc}",
                status_code=400,
            ) from exc
        self.config_path.write_text(
            _yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        try:
            _, store = self._store()
            store.append_log(
                f"API registered robot `{robot_id}` (driver `{driver}`) in "
                f"{self.config_path.name}. Restart watch to apply.",
                actor="api",
            )
        except Exception:
            pass
        self._publish_state("config_updated")
        return {
            "ok": True,
            "message": (
                f"Robot `{robot_id}` registered in {self.config_path.name}. "
                "Restart watch (`physical-agent watch`) to connect it."
            ),
            "requires_watch_restart": True,
            "robot_id": robot_id,
            "config_path": str(self.config_path),
            "config": self.get_config()["config"],
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

    def _llm_settings_path(self) -> Path:
        if not self.config_path.exists():
            raise ApiRequestError(
                f"Could not find {self.config_path}. Run `physical-agent init` first.",
                status_code=404,
            )
        config = load_config(self.config_path)
        return llm_settings_path(config.workspace_path(self.base_dir))

    def _resolved_llm_settings_values(self) -> dict[str, str]:
        settings_path = self._llm_settings_path()
        try:
            return resolve_llm_settings_values(
                env_file=self.base_dir / ".env",
                workspace_path=settings_path.parent,
            )
        except LLMSettingsError as exc:
            raise ApiRequestError(str(exc), status_code=400) from exc

    def _with_executor(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload["watch_enabled"] = self._embedded_watch_enabled
        payload["executor"] = self.executor_status()
        return payload

    def _executor_storage_snapshot(
        self,
    ) -> tuple[bool, dict[str, Any] | None, dict[str, Any] | None]:
        if not self.config_path.exists():
            return False, None, None
        try:
            config = load_config(self.config_path)
            store = open_state_store(config, base_dir=self.base_dir)
            initialized = store.exists()
            lease = (
                store.read_runtime_lease("watch-executor")
                if initialized
                else None
            )
            return initialized, lease, None
        except Exception as exc:
            return False, None, error_payload(exc, phase="executor_projection")

    def _state(self, config: PhysicalAgentConfig, store: StateStore) -> dict[str, Any]:
        actions = store.read_actions()
        feedback = store.read_feedback()
        claim_owners = store.read_action_claim_owners()
        plan = project_chat_plan(
            store.read_plan(),
            actions=actions,
            feedback=feedback,
            claim_owners=claim_owners,
        )
        return self._with_executor(
            {
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
                    "in_progress": _json_safe(actions.get("in_progress", [])),
                    "completed": _json_safe(actions["completed"]),
                    "cancelled": _json_safe(actions["cancelled"]),
                },
                "feedback": feedback,
                "safety": store.read_safety(),
                "chat": _json_safe(store.read_chat()),
                "plan": _json_safe(plan),
                "memory": _json_safe(store.read_memory()),
                "uploads": _json_safe(store.read_uploads()),
                "chunks": _json_safe(store.read_memory_chunks()),
            }
        )

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

    def _task_planner(self, config: PhysicalAgentConfig) -> PlannerPort:
        if self._planner_override is not None:
            return self._planner_override
        # LLM settings live in the workspace and can change at runtime. A fresh
        # planner avoids stale clients and mutable refusal state leaking across
        # concurrent API requests.
        return create_planner(config, base_dir=self.base_dir)



def _load_fastapi() -> dict[str, Any]:
    try:
        from fastapi import FastAPI, File, Form, Request, UploadFile
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
        "Request": Request,
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
    from physical_agent.dashboard import dashboard_dist_path

    candidates = [
        dashboard_dist_path(),
        Path(__file__).resolve().parents[2] / "frontend" / "dist",
        Path.cwd() / "frontend" / "dist",
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


def _next_stream_item(iterator: Iterator[dict[str, Any]]) -> dict[str, Any] | None:
    try:
        return next(iterator)
    except StopIteration:
        return None


def _close_iterator(iterator: Any) -> None:
    close = getattr(iterator, "close", None)
    if callable(close):
        close()


def _best_effort_close(closer: Callable[[], None] | None) -> None:
    if closer is None:
        return
    try:
        closer()
    except Exception:
        pass


def _validate_action(payload: dict[str, Any]) -> Action:
    try:
        return Action.model_validate(payload)
    except Exception as exc:
        raise ApiRequestError(f"Invalid action proposal: {exc}") from exc


def _metadata_text(metadata: Any, key: str, *, max_chars: int = 4000) -> str | None:
    if not isinstance(metadata, dict):
        return None
    value = metadata.get(key)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized[:max_chars] if normalized else None




def _new_chat_runtime(
    config_path: str | Path,
    *,
    planner_name: str,
    enable_code_skills: bool,
    enable_hardware_integration: bool,
) -> Any:
    from physical_agent.agent.chat_runtime import ChatRuntime

    return ChatRuntime(
        config_path,
        planner_name=planner_name,
        enable_code_skills=enable_code_skills,
        enable_hardware_integration=enable_hardware_integration,
    )


def _api_chat_planner(value: str | None) -> str:
    planner = (value or "auto").strip().lower()
    if planner in {"llm", "openai", "openai_compatible", "openai-compatible"}:
        return "llm"
    if planner in {"rule_based", "rules", "offline"}:
        return "rule_based"
    return "auto"


def _structured_output_api_error(exc: StructuredOutputError) -> ApiRequestError:
    schema_programming_error = exc.code in {
        "schema_invalid",
        "schema_model_mismatch",
    }
    status_code = 500 if schema_programming_error else 502
    return ApiRequestError(
        "The model returned an invalid structured response; no action was created.",
        status_code=status_code,
        details={
            "code": (
                "llm_schema_invalid"
                if schema_programming_error
                else "llm_output_invalid"
            ),
            "reason": exc.code,
            "attempts": exc.attempts,
            "issues": _public_structured_issues(exc),
        },
    )


def _public_structured_issues(exc: StructuredOutputError) -> list[dict[str, str]]:
    public: list[dict[str, str]] = []
    for issue in exc.issues[:12]:
        path = str(issue.get("path") or "/")
        code = str(issue.get("code") or "validation")
        public.append(
            {
                "path": path[:200],
                "code": re.sub(r"[^a-zA-Z0-9_.-]", "_", code)[:80],
            }
        )
    return public


def _sanitize_api_message(message: str, settings: dict[str, str]) -> str:
    sanitized = message
    api_key = settings.get("api_key") or ""
    if api_key:
        sanitized = sanitized.replace(api_key, "<redacted>")
    sanitized = re.sub(
        r"Bearer\s+[A-Za-z0-9._~+/=-]+",
        "Bearer <redacted>",
        sanitized,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(
        r"(api[_-]?key=)[^&\s]+",
        r"\1<redacted>",
        sanitized,
        flags=re.IGNORECASE,
    )
    return sanitized


def _write_plan(
    store: StateStore,
    summary: str,
    *,
    intent: str,
    agent_output: AgentOutput,
) -> None:
    actions = agent_output.actions
    steps = (
        task_graph_steps(agent_output)
        if agent_output.tasks
        else ["Record task."]
    )
    store.write_plan(
        ChatPlan(
            status="proposed_actions" if actions else "answered",
            intent=intent,
            summary=summary,
            steps=steps,
            needs_watch=bool(actions),
            agent_output=agent_output,
        )
    )




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






def _json_safe(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return value
