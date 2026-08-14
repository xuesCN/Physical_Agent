from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml
from typer.testing import CliRunner

import physical_agent.cli as cli_module
import physical_agent.api.server as api_server_module
from physical_agent.api.server import (
    ActionProposalRequest,
    ApiController,
    BROWSER_UPLOAD_MAX_BYTES,
    ChatRequest,
    ExportAuditRequest,
    IngestFileRequest,
    MissingServerDependencyError,
    SERVER_EXTRA_HINT,
    SearchMemoryRequest,
    SubmitTaskRequest,
    create_app,
)
from physical_agent.config import write_default_config
from physical_agent.llm import (
    OpenAICompatibleError,
    StructuredOutputError,
    llm_settings_path,
)
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
                "execution_mode": "simulation",
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
            summary="API test world",
            robots={"arm_1": {"status": "idle"}},
            objects={
                "red_block": {"type": "block", "color": "red", "location": "table"},
                "tray": {"type": "tray", "location": "table"},
            },
        )
    )
    return store


def _set_config_backend(config_path: Path, backend: str) -> None:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["workspace"]["backend"] = backend
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _sse_events(body: str) -> list[dict]:
    events = []
    for block in body.split("\n\n"):
        data_lines = [
            line.removeprefix("data:").strip()
            for line in block.splitlines()
            if line.startswith("data:")
        ]
        if data_lines:
            events.append(json.loads("\n".join(data_lines)))
    return events


def _openapi_response_properties(schema: dict, path: str) -> dict:
    response_schema = schema["paths"][path]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    reference = response_schema.get("$ref")
    if reference:
        component_name = reference.rsplit("/", 1)[-1]
        response_schema = schema["components"]["schemas"][component_name]
    return response_schema.get("properties", {})


def test_openapi_publishes_canonical_proposal_and_mutation_responses(tmp_path):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    schema = create_app(config_path).openapi()

    for path in ("/api/actions/propose", "/api/tasks/submit", "/api/chat"):
        properties = _openapi_response_properties(schema, path)
        assert "agent_output" in properties
        assert "action" not in properties
        assert "actions" not in properties
        assert "draft_actions" not in properties
        assert "executed" not in properties

    for path in (
        "/api/actions/{action_id}/approve",
        "/api/actions/{action_id}/reject",
    ):
        properties = _openapi_response_properties(schema, path)
        assert "action" in properties
        assert "agent_output" not in properties


def test_openapi_chat_plan_agent_output_references_canonical_component(tmp_path):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    schema = create_app(config_path).openapi()

    agent_output_schema = schema["components"]["schemas"]["ChatPlan"]["properties"][
        "agent_output"
    ]
    non_null_variants = [
        variant
        for variant in agent_output_schema["anyOf"]
        if variant.get("type") != "null"
    ]

    assert non_null_variants == [{"$ref": "#/components/schemas/AgentOutput"}]
    assert '"additionalProperties": true' not in json.dumps(agent_output_schema)
    agent_output_properties = schema["components"]["schemas"]["AgentOutput"][
        "properties"
    ]
    assert "schema" in agent_output_properties
    assert "schema_" not in agent_output_properties


def test_chat_plan_json_schema_resolves_after_direct_schema_module_import():
    script = """
import json
from physical_agent.protocol.schemas import ChatPlan

schema = ChatPlan.model_json_schema()
agent_output = schema["properties"]["agent_output"]
non_null = [item for item in agent_output["anyOf"] if item.get("type") != "null"]
assert non_null == [{"$ref": "#/$defs/AgentOutput"}], agent_output
assert "AgentOutput" in schema["$defs"]
assert "schema" in schema["$defs"]["AgentOutput"]["properties"]
assert "schema_" not in schema["$defs"]["AgentOutput"]["properties"]
print(json.dumps(agent_output, sort_keys=True))
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_api_cli_missing_server_extra_has_clear_message(tmp_path, monkeypatch):
    def fail_loader():
        raise MissingServerDependencyError(SERVER_EXTRA_HINT)

    monkeypatch.setattr(cli_module, "_load_api_server", fail_loader)

    result = CliRunner().invoke(
        cli_module.app,
        ["api", "--config", str(tmp_path / "physical-agent.yaml")],
    )

    assert result.exit_code == 1
    assert "FastAPI backend dependencies are not installed" in result.output
    assert ".[server]" in result.output


def test_api_cli_watch_flag_is_explicit(tmp_path, monkeypatch):
    calls = {}
    app_object = object()

    def fake_create_app(config, *, enable_watch=False, watch_interval_s=None):
        calls["create_app"] = {
            "config": Path(config),
            "enable_watch": enable_watch,
            "watch_interval_s": watch_interval_s,
        }
        return app_object

    class FakeUvicorn:
        @staticmethod
        def run(app, *, host, port):
            calls["uvicorn"] = {"app": app, "host": host, "port": port}

    monkeypatch.setattr(
        cli_module,
        "_load_api_server",
        lambda: (fake_create_app, FakeUvicorn),
    )

    config_path = tmp_path / "physical-agent.yaml"
    result = CliRunner().invoke(
        cli_module.app,
        [
            "api",
            "--config",
            str(config_path),
            "--host",
            "127.0.0.1",
            "--port",
            "8766",
            "--watch",
            "--watch-interval-s",
            "0.25",
        ],
    )

    assert result.exit_code == 0
    assert calls["create_app"] == {
        "config": config_path,
        "enable_watch": True,
        "watch_interval_s": 0.25,
    }
    assert calls["uvicorn"] == {
        "app": app_object,
        "host": "127.0.0.1",
        "port": 8766,
    }


def test_api_controller_contract_runs_without_fastapi(tmp_path):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    store = _prepare_store(config_path)
    controller = ApiController(config_path)

    assert controller.health()["ready"] is True
    assert controller.state()["actions"]["pending"] == []

    proposed = controller.propose_action(
        ActionProposalRequest(
            id="act_controller_direct",
            robot="arm_1",
            capability="observe",
            params={},
            reason="Controller proposal.",
            depends_on=[],
        )
    )
    assert "action" not in proposed
    assert proposed["agent_output"]["actions"][0]["id"] == "act_controller_direct"
    assert proposed["agent_output"]["schema"] == "physical-agent/agent-output/v1"
    assert any(
        task["kind"] == "safety_gate"
        for task in proposed["agent_output"]["tasks"]
    )

    submitted = controller.submit_task(
        SubmitTaskRequest(task="pick the red block and place it on the tray")
    )
    assert "actions" not in submitted
    assert [
        item["capability"] for item in submitted["agent_output"]["actions"]
    ] == ["pick", "place"]
    assert submitted["agent_output"]["proposal_id"] == submitted["proposal_id"]
    persisted_output = submitted["state"]["plan"]["plan"]["agent_output"]
    assert persisted_output["proposal_id"] is None
    assert {action["id"] for action in persisted_output["actions"]} == {
        "act_controller_direct",
        "act_001",
        "act_002",
    }

    chat = controller.chat(ChatRequest(message="remember that controller memory is safe"))
    assert "executed" not in chat
    assert chat["memory"][0]["content"] == "controller memory is safe"
    assert "actions" not in chat
    assert "draft_actions" not in chat
    assert "chat_contract" not in chat
    assert "has_structured_draft" not in chat
    assert controller.state()["chat"]["messages"]

    reset = controller.reset_chat()
    assert reset["ok"] is True
    assert reset["state"]["chat"]["messages"] == []
    assert reset["state"]["chat"]["running_summary"] == ""
    assert store.read_memory()["notes"][0]["content"] == "controller memory is safe"

    source = tmp_path / "controller.md"
    source.write_text("Controller upload retrieval text.", encoding="utf-8")
    ingested = controller.ingest_file(
        IngestFileRequest(path=str(source), tags=["controller"], importance=1)
    )
    assert ingested["result"]["chunks_written"] == 1

    search = controller.search_memory(
        SearchMemoryRequest(query="upload retrieval", tags=["controller"])
    )
    assert len(search["results"]) == 1

    audit_dir = tmp_path / "controller-audit"
    exported = controller.export_audit(ExportAuditRequest(out=str(audit_dir)))
    assert Path(exported["result"]["manifest"]).exists()
    assert (audit_dir / "actions.json").exists()

    board = store.read_actions()
    assert [item.id for item in board["pending"]] == [
        "act_controller_direct",
        "act_001",
        "act_002",
    ]
    assert board["completed"] == []
    assert board["cancelled"] == []


def test_api_project_initialize_is_idempotent_and_does_not_load_watch(
    tmp_path,
    monkeypatch,
):
    config_path = tmp_path / "physical-agent.yaml"

    def fail_loader():
        raise AssertionError("project initialization must not load WatchRuntime")

    monkeypatch.setattr(
        "physical_agent.api.watch_service._load_watch_runtime_class",
        fail_loader,
    )
    controller = ApiController(config_path, embedded_watch_enabled=True)

    first = controller.initialize_project()

    assert first["ok"] is True
    assert first["config_created"] is True
    assert first["workspace_created"] is True
    assert first["state"]["ready"] is True
    assert first["state"]["executor"]["mode"] == "embedded"

    config_text = config_path.read_text(encoding="utf-8")
    store = open_state_store(config_path=config_path)
    store.append_memory_note("preserve this", source="test")

    second = controller.initialize_project()

    assert second["config_created"] is False
    assert second["workspace_created"] is False
    assert second["message"] == "Project is already initialized."
    assert config_path.read_text(encoding="utf-8") == config_text
    assert store.read_memory()["notes"][0]["content"] == "preserve this"


def test_api_project_initialize_serializes_concurrent_requests(tmp_path):
    config_path = tmp_path / "physical-agent.yaml"
    controller = ApiController(config_path, embedded_watch_enabled=True)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _index: controller.initialize_project(), range(8)))

    assert sum(result["config_created"] for result in results) == 1
    assert sum(result["workspace_created"] for result in results) == 1
    assert all(result["state"]["ready"] is True for result in results)


def test_api_project_initialize_fails_closed_for_invalid_existing_config(tmp_path):
    config_path = tmp_path / "physical-agent.yaml"
    invalid = b"workspace: [not, a, mapping]\n"
    config_path.write_bytes(invalid)
    controller = ApiController(config_path, embedded_watch_enabled=True)

    with pytest.raises(api_server_module.ApiRequestError) as exc_info:
        controller.initialize_project()

    assert exc_info.value.status_code == 400
    assert "nothing was overwritten" in str(exc_info.value)
    assert config_path.read_bytes() == invalid
    assert not (tmp_path / "workspace").exists()


def test_api_project_initialize_endpoint_does_not_load_watch(tmp_path, monkeypatch):
    TestClient = _client_or_skip()
    config_path = tmp_path / "physical-agent.yaml"

    def fail_loader():
        raise AssertionError("initialize request handler must not load WatchRuntime")

    monkeypatch.setattr(
        "physical_agent.api.watch_service._load_watch_runtime_class",
        fail_loader,
    )
    with TestClient(create_app(config_path, enable_watch=False)) as client:
        response = client.post("/api/project/initialize")

    assert response.status_code == 200
    body = response.json()
    assert body["config_created"] is True
    assert body["workspace_created"] is True
    assert body["state"]["ready"] is True


def test_api_executor_projection_distinguishes_external_watch(tmp_path):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    store = _prepare_store(config_path)
    assert store.acquire_runtime_lease(
        "watch-executor",
        "external-watch-owner",
        ttl_s=30,
    )

    controller = ApiController(config_path, embedded_watch_enabled=True)
    executor = controller.health()["executor"]

    assert executor["mode"] == "external"
    assert executor["status"] == "active"
    assert executor["embedded_enabled"] is True
    assert executor["lease"]["active"] is True
    assert executor["lease"]["owner"] == "external-watch-owner"


def test_api_task_result_uses_shared_refusal_contract(tmp_path):
    class RefusingPlanner:
        last_refusal_reason = "The requested capability is intentionally unavailable."

        def plan(self, *, task, capabilities, world):
            return []

    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _prepare_store(config_path)
    result = ApiController(config_path, planner=RefusingPlanner()).submit_task(
        SubmitTaskRequest(task="do something unsupported")
    )

    assert result["ok"] is False
    assert result["proposal_status"] == "refused"
    assert result["refusal_reason"] == RefusingPlanner.last_refusal_reason
    assert result["proposal_id"].startswith("proposal_")
    assert result["agent_output"]["decision"] == "refuse"
    assert result["agent_output"]["tasks"] == []


def test_api_task_reports_unavailable_before_initializing_planner(tmp_path):
    class PlannerMustNotRun:
        def plan(self, *, task, capabilities, world):
            raise AssertionError("planner must not run without live capabilities")

    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    store = open_state_store(config_path=config_path)
    store.initialize()
    result = ApiController(config_path, planner=PlannerMustNotRun()).submit_task(
        SubmitTaskRequest(task="look around")
    )

    assert result["ok"] is False
    assert result["proposal_status"] == "unavailable"
    assert "actions" not in result
    assert result["agent_output"]["actions"] == []


def test_api_invalid_dependency_returns_client_error_without_partial_action(tmp_path):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    store = _prepare_store(config_path)
    controller = ApiController(config_path)

    with pytest.raises(api_server_module.ApiRequestError) as exc_info:
        controller.propose_action(
            ActionProposalRequest(
                id="act_invalid_dep",
                robot="arm_1",
                capability="observe",
                depends_on=["act_missing"],
            )
        )

    assert exc_info.value.status_code == 422
    assert store.read_actions()["pending"] == []


def test_api_chat_draft_dependency_requires_prerequisite_first(tmp_path):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    store = _prepare_store(config_path)
    controller = ApiController(config_path)
    dependent = ActionProposalRequest(
        id="draft_dependent",
        robot="arm_1",
        capability="observe",
        depends_on=["draft_prerequisite"],
        metadata={"source": "chat_draft"},
    )

    with pytest.raises(api_server_module.ApiRequestError) as exc_info:
        controller.propose_action(dependent)

    assert exc_info.value.status_code == 422
    assert store.read_actions()["pending"] == []

    first = controller.propose_action(
        ActionProposalRequest(
            id="draft_prerequisite",
            robot="arm_1",
            capability="observe",
            metadata={"source": "chat_draft"},
        )
    )
    second = controller.propose_action(dependent)

    assert "action" not in first
    assert "action" not in second
    assert first["agent_output"]["actions"][0]["id"] == "draft_prerequisite"
    assert second["agent_output"]["actions"][0]["depends_on"] == [
        "draft_prerequisite"
    ]
    assert [action.id for action in store.read_actions()["pending"]] == [
        "draft_prerequisite",
        "draft_dependent",
    ]


def test_api_state_ignores_stale_gate_from_prior_claim_owner(tmp_path):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    store = _prepare_store(config_path)
    controller = ApiController(config_path)
    controller.propose_action(
        ActionProposalRequest(
            id="act_api_claim",
            robot="arm_1",
            capability="observe",
            params={},
            reason="Project current claim evidence.",
            depends_on=[],
        )
    )
    stale = store.claim_next_ready_action(claim_owner="watch-old")
    assert stale is not None
    store.append_feedback_event(
        {
            "event": "safety_gate",
            "task_id": "task:safety_gate:act_api_claim",
            "action_id": "act_api_claim",
            "status": "passed",
            "decision": "allow",
            "actor": "watch",
            "owner": "watch",
            "executor_id": "watch-old",
            "mandatory": True,
            "policy_source": "SAFETY.md",
        }
    )
    assert store.recover_stale_actions(0, claim_owner="watch-old") == 1
    successor = store.claim_next_ready_action(claim_owner="watch-successor")
    assert successor is not None

    state = controller.state()
    projected = state["plan"]["plan"]["agent_output"]
    gate = next(task for task in projected["tasks"] if task["kind"] == "safety_gate")

    assert gate["status"] == "checking"
    assert "projection_error" not in gate["details"]
    assert "claim_owner" not in state["actions"]["in_progress"][0]
    assert "claim_owner" not in projected["actions"][0]


@pytest.mark.parametrize("failure", ["missing", "malformed"])
def test_api_health_fails_closed_for_unavailable_safety_policy(tmp_path, failure):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    store = _prepare_store(config_path)
    if failure == "missing":
        store.file("safety").unlink()
    else:
        store.file("safety").write_text("not a safety policy\n", encoding="utf-8")

    health = ApiController(config_path).health()

    assert health["ok"] is True
    assert health["ready"] is False
    assert health["safety_policy_valid"] is False
    assert "SAFETY policy" in health["message"]


def test_api_state_uses_final_claim_owner_read_to_fence_late_feedback(
    tmp_path,
    monkeypatch,
):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    store = _prepare_store(config_path)
    controller = ApiController(config_path)
    controller.propose_action(
        ActionProposalRequest(
            id="act_api_owner_race",
            robot="arm_1",
            capability="observe",
            params={},
            reason="Fence feedback with the final owner read.",
            depends_on=[],
        )
    )
    stale = store.claim_next_ready_action(claim_owner="watch-old")
    assert stale is not None
    store_type = type(store)
    real_read_claim_owners = store_type.read_action_claim_owners
    owner_snapshots: list[dict[str, str]] = []

    def transition_after_stale_owner_snapshot(self):
        owners = real_read_claim_owners(self)
        if self.path == store.path and not owner_snapshots:
            owner_snapshots.append(owners)
            assert self.recover_stale_actions(0, claim_owner="watch-old") == 1
            successor = self.claim_next_ready_action(claim_owner="watch-new")
            assert successor is not None
            self.append_feedback_event(
                {
                    "event": "safety_gate",
                    "task_id": "task:safety_gate:act_api_owner_race",
                    "action_id": "act_api_owner_race",
                    "status": "passed",
                    "decision": "allow",
                    "actor": "watch",
                    "owner": "watch",
                    "executor_id": "watch-old",
                    "mandatory": True,
                    "policy_source": "SAFETY.md",
                }
            )
        return owners

    monkeypatch.setattr(
        store_type,
        "read_action_claim_owners",
        transition_after_stale_owner_snapshot,
    )

    state = controller.state()
    projected = state["plan"]["plan"]["agent_output"]
    gate = next(task for task in projected["tasks"] if task["kind"] == "safety_gate")

    assert owner_snapshots == [{"act_api_owner_race": "watch-old"}]
    assert real_read_claim_owners(store) == {"act_api_owner_race": "watch-new"}
    assert gate["status"] == "checking"
    assert "last_decision" not in gate["details"]


def test_api_state_uses_final_owner_gate_after_late_prior_owner_reject(tmp_path):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    store = _prepare_store(config_path)
    controller = ApiController(config_path)
    controller.propose_action(
        ActionProposalRequest(
            id="act_api_terminal_owner",
            robot="arm_1",
            capability="observe",
            params={},
            reason="Keep terminal Gate evidence bound to the final owner.",
            depends_on=[],
        )
    )
    stale = store.claim_next_ready_action(claim_owner="watch-old")
    assert stale is not None
    assert store.recover_stale_actions(0, claim_owner="watch-old") == 1
    successor = store.claim_next_ready_action(claim_owner="watch-successor")
    assert successor is not None
    store.append_feedback_event(
        {
            "event": "safety_gate",
            "task_id": "task:safety_gate:act_api_terminal_owner",
            "action_id": "act_api_terminal_owner",
            "status": "passed",
            "decision": "allow",
            "actor": "watch",
            "owner": "watch",
            "executor_id": "watch-successor",
            "mandatory": True,
            "policy_source": "SAFETY.md",
        }
    )
    assert store.mark_action_completed(
        successor,
        claim_owner="watch-successor",
    ) is True
    store.append_feedback_event(
        {
            "event": "safety_gate",
            "task_id": "task:safety_gate:act_api_terminal_owner",
            "action_id": "act_api_terminal_owner",
            "status": "rejected",
            "decision": "deny",
            "actor": "watch",
            "owner": "watch",
            "executor_id": "watch-old",
            "mandatory": True,
            "policy_source": "SAFETY.md",
        }
    )

    state = controller.state()
    projected = state["plan"]["plan"]["agent_output"]
    gate = next(task for task in projected["tasks"] if task["kind"] == "safety_gate")

    assert projected["status"] == "completed"
    assert gate["status"] == "passed"
    assert gate["details"]["last_decision"]["executor_id"] == "watch-successor"
    assert "claim_owner" not in state["actions"]["completed"][0]
    assert "claim_owner" not in projected["actions"][0]


def test_api_endpoints_cover_state_proposals_memory_ingest_search_and_audit(tmp_path):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    store = _prepare_store(config_path)
    client = TestClient(create_app(config_path))

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["backend"] == "sqlite"
    assert health.json()["ready"] is True

    state = client.get("/api/state")
    assert state.status_code == 200
    assert state.json()["ready"] is True
    assert state.json()["actions"]["pending"] == []

    proposed = client.post(
        "/api/actions/propose",
        json={
            "id": "act_api_direct",
            "robot": "arm_1",
            "capability": "observe",
            "params": {},
            "reason": "API direct proposal.",
            "depends_on": [],
        },
    )
    assert proposed.status_code == 200
    assert "action" not in proposed.json()
    assert proposed.json()["agent_output"]["actions"][0]["id"] == "act_api_direct"

    submitted = client.post(
        "/api/tasks/submit",
        json={"task": "pick the red block and place it on the tray"},
    )
    assert submitted.status_code == 200
    assert "actions" not in submitted.json()
    output_actions = submitted.json()["agent_output"]["actions"]
    assert [item["capability"] for item in output_actions] == ["pick", "place"]
    assert [item["id"] for item in output_actions] == ["act_001", "act_002"]
    assert output_actions[1]["depends_on"] == ["act_001"]

    chat = client.post("/api/chat", json={"message": "remember that API memory is safe"})
    assert chat.status_code == 200
    assert "executed" not in chat.json()
    assert "I will remember" in chat.json()["reply"]
    assert chat.json()["memory"][0]["content"] == "API memory is safe"
    assert "actions" not in chat.json()
    assert "draft_actions" not in chat.json()
    assert "chat_contract" not in chat.json()
    assert "has_structured_draft" not in chat.json()

    reset = client.post("/api/chat/reset")
    assert reset.status_code == 200
    assert reset.json()["state"]["chat"]["messages"] == []
    assert reset.json()["state"]["chat"]["running_summary"] == ""
    assert store.read_memory()["notes"][0]["content"] == "API memory is safe"

    source = tmp_path / "upload.md"
    source.write_text("# Calibration\n\nUse local path ingest for retrieval chunks.", encoding="utf-8")
    ingested = client.post(
        "/api/ingest-file",
        json={"path": str(source), "tags": ["api"], "importance": 2},
    )
    assert ingested.status_code == 200
    assert ingested.json()["result"]["chunks_written"] == 1
    assert ingested.json()["result"]["metadata"]["status"] == "stored"

    search = client.post(
        "/api/search-memory",
        json={"query": "calibration retrieval", "limit": 3, "tags": ["api"]},
    )
    assert search.status_code == 200
    assert len(search.json()["results"]) == 1
    assert search.json()["results"][0]["trust_level"] == "untrusted"

    audit_dir = tmp_path / "api-audit"
    exported = client.post("/api/export-audit", json={"out": str(audit_dir)})
    assert exported.status_code == 200
    assert exported.json()["backend"] == "sqlite"
    assert Path(exported.json()["manifest"]).exists()
    assert Path(exported.json()["result"]["manifest"]).exists()
    assert (audit_dir / "uploads.json").exists()

    board = store.read_actions()
    assert [item.id for item in board["pending"]] == [
        "act_api_direct",
        "act_001",
        "act_002",
    ]
    assert board["completed"] == []
    assert board["cancelled"] == []


def test_api_approve_reject_actions_are_idempotent_and_state_protected(tmp_path):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    store = _prepare_store(config_path)
    store.write_capabilities(
        {
            "arm_1": {
                "kind": "arm",
                "driver": "mock_arm",
                "status": "connected",
                "capabilities": [
                    {
                        "name": "observe",
                        "description": "Inspect with approval.",
                        "params_schema": {"type": "object"},
                        "requires_approval": True,
                    }
                ],
            }
        }
    )
    client = TestClient(create_app(config_path))

    proposed = client.post(
        "/api/actions/propose",
        json={
            "id": "act_api_approval",
            "robot": "arm_1",
            "capability": "observe",
            "params": {},
            "reason": "Needs human approval.",
            "depends_on": [],
            "metadata": {"source": "chat_draft", "user_message": "look around"},
        },
    )
    assert proposed.status_code == 200
    assert "action" not in proposed.json()
    action = proposed.json()["agent_output"]["actions"][0]
    assert action["metadata"]["source"] == "chat_draft"
    assert action["metadata"]["approval"]["required"] is True
    assert action["metadata"]["approval"]["status"] == "pending"

    approved = client.post(
        "/api/actions/act_api_approval/approve",
        json={"reason": "Intentional.", "actor": "gui"},
    )
    approved_again = client.post("/api/actions/act_api_approval/approve", json={})

    assert approved.status_code == 200
    assert approved.json()["changed"] is True
    assert approved.json()["action"]["metadata"]["approval"]["status"] == "approved"
    assert approved_again.status_code == 200
    assert approved_again.json()["changed"] is False

    log_entries = store.export_human_view()["manifest"]
    assert log_entries
    audit_dir = store.path / "audit"
    log_text = (audit_dir / "log.json").read_text(encoding="utf-8")
    assert log_text.count("API approved action `act_api_approval`") == 1

    store.mark_action_completed(store.read_actions()["pending"][0])
    rejected_completed = client.post(
        "/api/actions/act_api_approval/reject",
        json={"reason": "Too late.", "actor": "gui"},
    )
    missing = client.post("/api/actions/missing_action/approve", json={})

    assert rejected_completed.status_code == 409
    assert missing.status_code == 404


def test_api_approve_succeeds_when_log_mirror_write_fails_after_commit(
    tmp_path,
    monkeypatch,
):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    store = _prepare_store(config_path)
    store.write_capabilities(
        {
            "arm_1": {
                "kind": "arm",
                "driver": "mock_arm",
                "status": "connected",
                "capabilities": [
                    {
                        "name": "observe",
                        "description": "Inspect with approval.",
                        "params_schema": {"type": "object"},
                        "requires_approval": True,
                    }
                ],
            }
        }
    )
    client = TestClient(create_app(config_path), raise_server_exceptions=False)
    proposed = client.post(
        "/api/actions/propose",
        json={
            "id": "act_api_mirror_failure",
            "robot": "arm_1",
            "capability": "observe",
            "params": {},
            "reason": "Approval must survive mirror failure.",
            "depends_on": [],
        },
    )
    assert proposed.status_code == 200

    log_path = store.file("log").resolve()
    real_open = Path.open

    def fail_log_write(path: Path, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        resolved = path.resolve()
        is_log_target = resolved == log_path
        is_log_temp = (
            resolved.parent == log_path.parent
            and path.name.startswith(f".{log_path.name}.")
        )
        if "w" in mode and (is_log_target or is_log_temp):
            raise OSError("simulated LOG mirror write failure")
        return real_open(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", fail_log_write)
        approved = client.post(
            "/api/actions/act_api_mirror_failure/approve",
            json={"reason": "Intentional.", "actor": "gui"},
        )

    assert approved.status_code == 200, approved.text
    assert approved.json()["changed"] is True
    assert approved.json()["action"]["metadata"]["approval"]["status"] == "approved"
    pending = {action.id: action for action in store.read_actions()["pending"]}
    assert pending["act_api_mirror_failure"].metadata["approval"]["status"] == "approved"


def test_api_reject_pending_action_moves_to_cancelled_with_reason(tmp_path):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _prepare_store(config_path)
    client = TestClient(create_app(config_path))
    client.post(
        "/api/actions/propose",
        json={
            "id": "act_reject_me",
            "robot": "arm_1",
            "capability": "observe",
            "params": {},
            "reason": "Maybe inspect.",
            "depends_on": [],
        },
    )

    rejected = client.post(
        "/api/actions/act_reject_me/reject",
        json={"reason": "Wrong target.", "actor": "gui"},
    )

    assert rejected.status_code == 200
    assert rejected.json()["action"]["id"] == "act_reject_me"
    assert rejected.json()["action"]["metadata"]["approval"]["status"] == "rejected"
    cancelled = rejected.json()["state"]["actions"]["cancelled"][0]
    assert cancelled["id"] == "act_reject_me"
    assert cancelled["metadata"]["approval"]["status"] == "rejected"
    assert cancelled["metadata"]["approval"]["reason"] == "Wrong target."


def test_api_state_check_reports_backend_guidance_without_watch(
    tmp_path,
    monkeypatch,
):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _set_config_backend(config_path, "sqlite")
    store = open_state_store(config_path=config_path)
    store.initialize()

    import physical_agent.watch.runtime as watch_runtime

    def fail_watch_init(self, *args, **kwargs):
        raise AssertionError("state-check API must not instantiate WatchRuntime")

    monkeypatch.setattr(watch_runtime.WatchRuntime, "__init__", fail_watch_init)

    client = TestClient(create_app(config_path))
    response = client.get("/api/state-check")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["backend"] == "sqlite"
    assert body["backend_role"] == "recommended"
    assert "state.db" in body["source_of_truth"]
    assert body["runtime_switch_supported"] is False
    assert "GUI live backend switch" in body["switching_model"]
    assert "state.db" in body["recommendation"]
    assert "SAFETY.md" in body["recommendation"]
    assert body["sqlite_schema_complete"] is True


def test_api_llm_settings_endpoints_do_not_leak_key(tmp_path):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _prepare_store(config_path)
    client = TestClient(create_app(config_path))

    saved = client.post(
        "/api/settings/llm",
        json={
            "base_url": "http://local-llm.test/v1",
            "api_key": "sk-local-secret-7890",
            "model": "local-model",
            "api_mode": "chat_completions",
            "reasoning_enabled": True,
            "reasoning_effort": "high",
            "reasoning_summary": "detailed",
            "reasoning_extra_body": {"thinking": {"type": "enabled"}},
        },
    )
    assert saved.status_code == 200
    assert saved.json()["has_api_key"] is True
    assert saved.json()["masked_api_key"] == "****7890"
    assert saved.json()["reasoning_enabled"] is True
    assert saved.json()["reasoning_effort"] == "high"
    assert saved.json()["reasoning_summary"] == "detailed"
    assert saved.json()["has_reasoning_extra_body"] is True
    assert "sk-local-secret-7890" not in saved.text

    settings_file = llm_settings_path(tmp_path / "workspace")
    assert settings_file.exists()
    settings_text = settings_file.read_text(encoding="utf-8")
    assert "sk-local-secret-7890" in settings_text
    assert "thinking" in settings_text

    fetched = client.get("/api/settings/llm")
    assert fetched.status_code == 200
    assert fetched.json()["base_url"] == "http://local-llm.test/v1"
    assert fetched.json()["model"] == "local-model"
    assert fetched.json()["api_mode"] == "chat_completions"
    assert fetched.json()["reasoning_enabled"] is True
    assert fetched.json()["reasoning_effort"] == "high"
    assert fetched.json()["reasoning_summary"] == "detailed"
    assert fetched.json()["has_reasoning_extra_body"] is True
    assert "sk-local-secret-7890" not in fetched.text


def test_api_llm_settings_test_uses_mocked_client_success_and_failure(tmp_path, monkeypatch):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _prepare_store(config_path)
    client = TestClient(create_app(config_path))
    client.post(
        "/api/settings/llm",
        json={
            "base_url": "http://local-llm.test/v1",
            "api_key": "sk-local-secret-7890",
            "model": "local-model",
            "api_mode": "chat_completions",
        },
    )

    class PassingClient:
        def __init__(self, settings):
            self.settings = settings

        def test_connection(self):
            return {
                "ok": True,
                "model": self.settings.model,
                "endpoint": self.settings.chat_completions_url,
                "api_mode": self.settings.api_mode,
                "content": "pong",
            }

    monkeypatch.setattr(api_server_module, "OpenAICompatibleClient", PassingClient)
    passed = client.post("/api/settings/llm/test")
    assert passed.status_code == 200
    assert passed.json()["ok"] is True
    assert passed.json()["model"] == "local-model"
    assert "sk-local-secret-7890" not in passed.text

    class FailingClient:
        def __init__(self, settings):
            self.settings = settings

        def test_connection(self):
            raise OpenAICompatibleError("Bearer sk-local-secret-7890 failed")

    monkeypatch.setattr(api_server_module, "OpenAICompatibleClient", FailingClient)
    failed = client.post("/api/settings/llm/test")
    assert failed.status_code == 200
    assert failed.json()["ok"] is False
    assert "<redacted>" in failed.json()["message"]
    assert "sk-local-secret-7890" not in failed.text


def test_api_chat_uses_chat_runtime_llm_when_settings_exist(tmp_path, monkeypatch):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _prepare_store(config_path)
    client = TestClient(create_app(config_path))
    client.post(
        "/api/settings/llm",
        json={
            "base_url": "http://local-llm.test/v1",
            "api_key": "sk-local-secret-7890",
            "model": "local-model",
            "api_mode": "chat_completions",
        },
    )

    from physical_agent.agent.chat_runtime import ChatRuntime

    class FakeChatClient:
        def structured_json(self, messages, **kwargs):
            return {
                "reply": "LLM bridge response.",
                "intent": "chat",
                "steps": [],
                "actions": [],
                "memory": [],
            }

    monkeypatch.setattr(ChatRuntime, "_llm_client", lambda self: FakeChatClient())

    response = client.post("/api/chat", json={"message": "hello from API"})

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "llm"
    assert body["reply"] == "LLM bridge response."
    assert "executed" not in body
    messages = body["state"]["chat"]["messages"]
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "hello from API"


def test_api_chat_maps_structured_output_exhaustion_to_sanitized_502(
    tmp_path, monkeypatch
):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    store = _prepare_store(config_path)

    class FakeRuntime:
        def respond(self, message):
            raise StructuredOutputError(
                "RAW_PROVIDER_SECRET is not allowed",
                code="retries_exhausted",
                retryable=False,
                attempts=2,
                issues=[
                    {
                        "path": "/intent",
                        "code": "schema_enum",
                        "message": "RAW_PROVIDER_SECRET",
                    }
                ],
            )

    monkeypatch.setattr(
        api_server_module,
        "_new_chat_runtime",
        lambda config, **kwargs: FakeRuntime(),
    )
    client = TestClient(create_app(config_path))

    response = client.post(
        "/api/chat",
        json={"message": "hello", "planner": "llm"},
    )

    assert response.status_code == 502
    body = response.json()
    assert body["details"] == {
        "code": "llm_output_invalid",
        "reason": "retries_exhausted",
        "attempts": 2,
        "issues": [{"path": "/intent", "code": "schema_enum"}],
    }
    assert "RAW_PROVIDER_SECRET" not in response.text
    assert store.read_actions()["pending"] == []


def test_api_task_structured_output_failure_creates_no_pending_action(
    tmp_path, monkeypatch
):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    store = _prepare_store(config_path)

    def fail_submit_task(self, task, **kwargs):
        raise StructuredOutputError(
            "invalid planner output",
            code="schema_mismatch",
            retryable=True,
            issues=[
                {
                    "path": "/actions/0/robot",
                    "code": "schema_minLength",
                    "message": "invalid",
                }
            ],
        )

    monkeypatch.setattr(
        api_server_module.ProposalService,
        "submit_task",
        fail_submit_task,
    )
    client = TestClient(create_app(config_path))

    response = client.post("/api/tasks/submit", json={"task": "look around"})

    assert response.status_code == 502
    assert response.json()["details"]["code"] == "llm_output_invalid"
    assert response.json()["details"]["reason"] == "schema_mismatch"
    assert store.read_actions()["pending"] == []


def test_api_schema_programming_error_is_500_not_output_502(tmp_path, monkeypatch):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _prepare_store(config_path)

    class FakeRuntime:
        def respond(self, message):
            raise StructuredOutputError(
                "local schema is invalid",
                code="schema_invalid",
                retryable=False,
                issues=[{"path": "/", "code": "schema_invalid", "message": "bad"}],
            )

    monkeypatch.setattr(
        api_server_module,
        "_new_chat_runtime",
        lambda config, **kwargs: FakeRuntime(),
    )
    client = TestClient(create_app(config_path))

    response = client.post("/api/chat", json={"message": "hello", "planner": "llm"})

    assert response.status_code == 500
    assert response.json()["details"]["code"] == "llm_schema_invalid"
    assert response.json()["details"]["reason"] == "schema_invalid"


def test_api_chat_falls_back_to_rule_based_without_llm_settings(tmp_path, monkeypatch):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _prepare_store(config_path)
    for key in ("OPENAI_API_KEY", "GPT_KEY", "API_KEY"):
        monkeypatch.delenv(key, raising=False)

    client = TestClient(create_app(config_path))
    response = client.post("/api/chat", json={"message": "what is the world status?"})

    assert response.status_code == 200
    assert response.json()["mode"] == "rule_based"
    assert "API test world" in response.json()["reply"]


def test_api_chat_constructs_api_safe_chat_runtime(tmp_path, monkeypatch):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _prepare_store(config_path)
    calls = {}

    class FakeRuntime:
        def respond(self, message):
            calls["respond"] = {"message": message}
            return {
                "ok": True,
                "mode": "rule_based",
                "reply": "safe bridge",
                "actions": [],
                "memory": [],
                "plan": None,
            }

    def fake_new_runtime(config, **kwargs):
        calls["runtime"] = {"config": Path(config), **kwargs}
        return FakeRuntime()

    monkeypatch.setattr(api_server_module, "_new_chat_runtime", fake_new_runtime)

    client = TestClient(create_app(config_path))
    response = client.post("/api/chat", json={"message": "hello"})

    assert response.status_code == 200
    assert calls["runtime"] == {
        "config": config_path.resolve(),
        "planner_name": "auto",
        "enable_code_skills": False,
        "enable_hardware_integration": False,
    }
    assert calls["respond"] == {"message": "hello"}


def test_api_chat_stream_sends_start_thought_delta_done_events(tmp_path, monkeypatch):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _prepare_store(config_path)
    calls = {}

    class FakeRuntime:
        def respond_stream(self, message, **kwargs):
            calls["respond"] = {
                "message": message,
                "has_cancel_check": "cancel_check" in kwargs,
                "has_transport_observer": "transport_observer" in kwargs,
            }
            yield {"type": "thought", "delta": "Checked the constraints."}
            yield {"type": "delta", "delta": "hel"}
            yield {"type": "delta", "delta": "lo"}
            yield {
                "type": "done",
                "mode": "llm",
                "reply": "hello",
                "agent_output": {
                    "schema": "physical-agent/agent-output/v1",
                    "status": "draft",
                    "decision": "propose",
                    "lifecycle": "draft",
                    "message": "hello",
                    "tasks": [],
                    "actions": [{"id": "canonical_001"}],
                },
                "memory": [],
                "plan": {"status": "answered"},
                # Deliberate legacy internal input: the public SSE payload must drop it.
                "executed": 0,
            }

    def fake_new_runtime(config, **kwargs):
        calls["runtime"] = {"config": Path(config), **kwargs}
        return FakeRuntime()

    monkeypatch.setattr(api_server_module, "_new_chat_runtime", fake_new_runtime)

    client = TestClient(create_app(config_path))
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={
            "message": "hello",
            "request_id": "req-test",
            "stream_id": "stream-test",
        },
    ) as response:
        assert response.status_code == 200
        events = _sse_events("".join(response.iter_text()))

    assert [event["type"] for event in events] == [
        "start",
        "thought",
        "delta",
        "delta",
        "done",
    ]
    assert events[0]["payload"]["stream_id"] == "stream-test"
    assert events[0]["payload"]["request_id"] == "req-test"
    assert events[1]["payload"]["delta"] == "Checked the constraints."
    assert "type" not in events[1]["payload"]
    assert events[2]["payload"]["delta"] == "hel"
    assert events[4]["payload"]["reply"] == "hello"
    assert events[4]["payload"]["agent_output"]["schema"] == (
        "physical-agent/agent-output/v1"
    )
    assert events[4]["payload"]["plan"] == {"status": "answered"}
    assert "executed" not in events[4]["payload"]
    assert "actions" not in events[4]["payload"]
    assert "draft_actions" not in events[4]["payload"]
    assert "chat_contract" not in events[4]["payload"]
    assert "has_structured_draft" not in events[4]["payload"]
    assert events[4]["payload"]["state"]["chat"]["messages"] == []
    assert calls["runtime"] == {
        "config": config_path.resolve(),
        "planner_name": "auto",
        "enable_code_skills": False,
        "enable_hardware_integration": False,
    }
    assert calls["respond"] == {
        "message": "hello",
        "has_cancel_check": True,
        "has_transport_observer": True,
    }


def test_api_chat_stream_sends_sanitized_error_event(tmp_path, monkeypatch):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _prepare_store(config_path)

    class FakeRuntime:
        def respond_stream(self, message, **kwargs):
            raise OpenAICompatibleError("Bearer sk-local-secret-7890 failed")
            yield  # pragma: no cover

    monkeypatch.setattr(
        api_server_module,
        "_new_chat_runtime",
        lambda config, **kwargs: FakeRuntime(),
    )

    client = TestClient(create_app(config_path))
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"message": "hello", "stream_id": "stream-error"},
    ) as response:
        assert response.status_code == 200
        events = _sse_events("".join(response.iter_text()))

    assert [event["type"] for event in events] == ["start", "error"]
    assert "<redacted>" in events[-1]["payload"]["message"]
    assert "sk-local-secret-7890" not in events[-1]["payload"]["message"]


def test_api_chat_stream_sanitizes_runtime_error_event_and_preserves_code(
    tmp_path, monkeypatch
):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _prepare_store(config_path)

    class FakeRuntime:
        def respond_stream(self, message, **kwargs):
            yield {
                "type": "error",
                "message": "Bearer sk-runtime-secret failed",
                "code": "llm_output_invalid",
                "reason": "schema_mismatch",
                "attempts": 1,
                "mode": "llm",
                "reply": "",
            }

    monkeypatch.setattr(
        api_server_module,
        "_new_chat_runtime",
        lambda config, **kwargs: FakeRuntime(),
    )

    client = TestClient(create_app(config_path))
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"message": "hello", "stream_id": "stream-runtime-error"},
    ) as response:
        assert response.status_code == 200
        events = _sse_events("".join(response.iter_text()))

    assert [event["type"] for event in events] == ["start", "error"]
    payload = events[-1]["payload"]
    assert payload["message"] == "Bearer <redacted> failed"
    assert payload["code"] == "llm_output_invalid"
    assert payload["reason"] == "schema_mismatch"
    assert payload["attempts"] == 1
    assert "sk-runtime-secret" not in json.dumps(payload)


def test_api_chat_stream_abort_registry_stops_before_consuming_runtime(tmp_path, monkeypatch):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _prepare_store(config_path)
    controller = ApiController(config_path)
    stream_state = controller.register_chat_stream(
        ChatRequest(message="hello", stream_id="stream-abort", request_id="req-abort")
    )
    transport = {"closed": 0}
    stream_state.observe_transport(
        lambda: transport.__setitem__("closed", transport["closed"] + 1)
    )
    assert controller.abort_chat_stream("stream-abort", reason="test") is True
    assert transport["closed"] == 1

    class FakeRuntime:
        def respond_stream(self, message, **kwargs):
            raise AssertionError("aborted stream must not consume runtime chunks")
            yield  # pragma: no cover

    monkeypatch.setattr(
        api_server_module,
        "_new_chat_runtime",
        lambda config, **kwargs: FakeRuntime(),
    )

    events = list(
        controller.chat_stream(
            ChatRequest(message="hello"),
            stream_state=stream_state,
        )
    )

    assert events[0]["type"] == "aborted"
    assert events[0]["payload"]["stream_id"] == "stream-abort"
    assert controller.abort_chat_stream("missing-stream", reason="test") is False


def test_api_chat_abort_endpoint_reports_missing_stream(tmp_path):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _prepare_store(config_path)
    client = TestClient(create_app(config_path))

    response = client.post("/api/chat/abort/missing-stream")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "stream_id": "missing-stream",
        "aborted": False,
    }


def test_api_browser_upload_records_untrusted_metadata_chunks_and_audit(tmp_path):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    store = _prepare_store(config_path)
    client = TestClient(create_app(config_path))

    response = client.post(
        "/api/upload",
        files={"file": ("browser.md", b"# Browser Upload\n\nUse this as context only.", "text/markdown")},
        data={"tags": "browser, dragger", "importance": "3"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["result"]["chunks_written"] == 1
    metadata = body["result"]["metadata"]
    assert metadata["original_name"] == "browser.md"
    assert metadata["stored_name"].endswith("-browser.md")
    assert metadata["status"] == "stored"
    assert metadata["tags"] == ["browser", "dragger"]
    assert metadata["importance"] == 3
    stored_path = Path(metadata["stored_path"])
    assert stored_path.parent == store.uploads_path
    assert stored_path.exists()

    uploads = store.read_uploads()["uploads"]
    assert uploads[0]["sha256"] == metadata["sha256"]
    memory = store.read_memory(source="upload")["notes"][0]
    assert memory["kind"] == "upload_excerpt"
    assert memory["tags"] == ["upload", ".md", "browser", "dragger"]
    assert memory["content"].startswith("UNTRUSTED UPLOAD EXCERPT")
    chunks = store.read_memory_chunks()["chunks"]
    assert chunks[0]["source_type"] == "upload"
    assert chunks[0]["source_id"] == metadata["sha256"]
    assert chunks[0]["trust_level"] == "untrusted"
    assert "Browser Upload" in chunks[0]["content"]

    audit_dir = tmp_path / "browser-upload-audit"
    exported = client.post("/api/export-audit", json={"out": str(audit_dir)})
    assert exported.status_code == 200
    assert Path(exported.json()["result"]["manifest"]).exists()
    assert (audit_dir / "uploads.json").exists()
    assert (audit_dir / "chunks.json").exists()


def test_api_browser_upload_rejects_unsupported_type_with_clear_error(tmp_path):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    store = _prepare_store(config_path)
    client = TestClient(create_app(config_path))

    response = client.post(
        "/api/upload",
        files={"file": ("manual.pdf", b"%PDF-1.7\n", "application/pdf")},
    )

    assert response.status_code == 400
    assert "Unsupported upload type" in response.json()["message"]
    assert "PDF, OCR, and image ingestion are not implemented" in response.json()["message"]
    assert store.read_uploads()["uploads"] == []
    assert store.read_memory(source="upload")["notes"] == []


def test_api_browser_upload_rejects_oversize_without_ingesting(tmp_path):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    store = _prepare_store(config_path)
    client = TestClient(create_app(config_path))
    oversized = b"a" * (BROWSER_UPLOAD_MAX_BYTES + 1)

    response = client.post(
        "/api/upload",
        files={"file": ("huge.txt", oversized, "text/plain")},
    )

    assert response.status_code == 413
    assert "exceeds the 5MB limit" in response.json()["message"]
    assert store.read_uploads()["uploads"] == []
    assert store.read_memory(source="upload")["notes"] == []
    assert store.read_memory_chunks()["chunks"] == []


def test_api_homepage_serves_gui_or_clear_build_prompt(tmp_path, monkeypatch):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _prepare_store(config_path)
    empty_dist = tmp_path / "empty-dist"
    monkeypatch.setattr(api_server_module, "_frontend_dist_path", lambda: empty_dist)

    client = TestClient(create_app(config_path))
    response = client.get("/")

    assert response.status_code == 200
    assert "GUI build not found" in response.text
    assert "npm run build" in response.text

    gui_dist = tmp_path / "gui-dist"
    (gui_dist / "assets").mkdir(parents=True)
    (gui_dist / "index.html").write_text("<!doctype html><title>Physical Agent GUI</title>", encoding="utf-8")
    monkeypatch.setattr(api_server_module, "_frontend_dist_path", lambda: gui_dist)

    client = TestClient(create_app(config_path))
    response = client.get("/")

    assert response.status_code == 200
    assert "Physical Agent GUI" in response.text


def test_api_requests_do_not_instantiate_watch_or_execute_driver(tmp_path, monkeypatch):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _prepare_store(config_path)
    for key in ("OPENAI_API_KEY", "GPT_KEY", "API_KEY"):
        monkeypatch.delenv(key, raising=False)

    import physical_agent.watch.runtime as watch_runtime
    from physical_agent.drivers.mock_arm import MockArmDriver

    def fail_watch_init(self, *args, **kwargs):
        raise AssertionError("API must not instantiate WatchRuntime")

    async def fail_execute(self, action):
        raise AssertionError("API must not call driver.execute")

    monkeypatch.setattr(watch_runtime.WatchRuntime, "__init__", fail_watch_init)
    monkeypatch.setattr(MockArmDriver, "execute", fail_execute)

    client = TestClient(create_app(config_path))

    assert client.get("/api/state-check").status_code == 200
    assert client.post(
        "/api/actions/propose",
        json={
            "id": "act_safe",
            "robot": "arm_1",
            "capability": "observe",
            "params": {},
            "reason": "request-side proposal only",
            "depends_on": [],
        },
    ).status_code == 200
    assert client.post(
        "/api/tasks/submit",
        json={"task": "pick the red block and place it on the tray"},
    ).status_code == 200
    assert client.post(
        "/api/chat",
        json={"message": "look around"},
    ).status_code == 200
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"message": "look around"},
    ) as response:
        assert response.status_code == 200
        stream_event_types = [
            event["type"] for event in _sse_events("".join(response.iter_text()))
        ]
        assert stream_event_types[0] == "start"
        assert "delta" in stream_event_types
        assert stream_event_types[-1] == "done"
    assert client.post(
        "/api/upload",
        files={"file": ("safe.md", b"upload text remains untrusted", "text/markdown")},
    ).status_code == 200
    assert client.post("/api/export-audit", json={}).status_code == 200

    store = open_state_store(config_path=config_path)
    assert [item.id for item in store.read_actions()["completed"]] == []
    assert [item.id for item in store.read_actions()["cancelled"]] == []


def test_api_workspace_reset_requires_confirm(tmp_path):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _prepare_store(config_path)
    client = TestClient(create_app(config_path))

    response = client.post("/api/workspace/reset", json={})

    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert "confirm" in response.json()["message"].lower()


def test_api_workspace_reset_clears_state_without_watch(tmp_path, monkeypatch):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    store = _prepare_store(config_path)
    store.append_chat_message("user", "hello before reset")
    guidance = "Keep both test wheels raised and keep a physical power cutoff available."
    store.file("safety").write_text(
        store.file("safety").read_text(encoding="utf-8").rstrip()
        + f"\n\n## Agent Guidance\n\n{guidance}\n",
        encoding="utf-8",
    )
    safety_before = store.read_safety_snapshot()
    client = TestClient(create_app(config_path))
    client.post(
        "/api/actions/propose",
        json={
            "id": "act_before_reset",
            "robot": "arm_1",
            "capability": "observe",
            "params": {},
            "reason": "will be cleared by reset",
            "depends_on": [],
        },
    )

    import physical_agent.watch.runtime as watch_runtime

    def fail_watch_init(self, *args, **kwargs):
        raise AssertionError("workspace reset must not instantiate WatchRuntime")

    monkeypatch.setattr(watch_runtime.WatchRuntime, "__init__", fail_watch_init)

    response = client.post("/api/workspace/reset", json={"confirm": True})

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert "hard Rules" in response.json()["message"]
    assert "Agent Guidance is preserved" in response.json()["message"]
    fresh = open_state_store(config_path=config_path)
    assert fresh.exists()
    assert fresh.read_chat()["messages"] == []
    assert fresh.read_actions()["pending"] == []
    safety_after = fresh.read_safety_snapshot()
    assert safety_after.hard.revision == safety_before.hard.revision + 1
    assert safety_after.agent_guidance == guidance
    assert safety_after.hard.rules["allow_autonomous_execution"] is True
    # Config file must survive a workspace reset.
    assert config_path.exists()
    assert "arm_1" in config_path.read_text(encoding="utf-8")


def test_api_workspace_reset_refuses_live_watch_lease(tmp_path):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    store = _prepare_store(config_path)
    assert store.acquire_runtime_lease(
        "watch-executor",
        "active-watch",
        ttl_s=30,
    ) is True
    client = TestClient(create_app(config_path))

    response = client.post("/api/workspace/reset", json={"confirm": True})

    assert response.status_code == 409
    assert response.json()["ok"] is False
    assert "Stop Watch first" in response.json()["message"]
    assert store.release_runtime_lease("watch-executor", "active-watch") is True


def test_api_integrate_generates_scaffold(tmp_path):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _prepare_store(config_path)
    sdk = tmp_path / "vendor_sdk"
    sdk.mkdir()
    (sdk / "README.md").write_text(
        "# Demo Voice Device\n\nHTTP SDK with voice, speak, tts, light and RGB support.",
        encoding="utf-8",
    )
    client = TestClient(create_app(config_path))

    response = client.post(
        "/api/integrate",
        json={"source": str(sdk), "name": "voice_light_driver"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    output_path = Path(body["result"]["output_path"])
    assert output_path.exists()
    assert (output_path / "driver.py").exists()
    assert (output_path / "physical_driver.yaml").exists()


def test_api_integrate_rejects_empty_source(tmp_path):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _prepare_store(config_path)
    client = TestClient(create_app(config_path))

    response = client.post("/api/integrate", json={"source": "   "})

    assert response.status_code == 400
    assert response.json()["ok"] is False


def test_api_get_config_returns_effective_view(tmp_path):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _prepare_store(config_path)
    client = TestClient(create_app(config_path))

    response = client.get("/api/config")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["config_path"] == str(config_path)
    assert body["config"]["workspace"]["backend"] == "sqlite"
    assert "arm_1" in body["config"]["robots"]


def test_api_register_robot_appends_yaml_and_keeps_existing(tmp_path):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _prepare_store(config_path)
    client = TestClient(create_app(config_path))

    response = client.post(
        "/api/config/robots",
        json={
            "robot_id": "arm_2",
            "driver": "mock_rover",
            "execution_mode": "simulation",
            "config": {"mode": "mock"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["requires_watch_restart"] is True
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["robots"]["arm_2"] == {
        "driver": "mock_rover",
        "execution_mode": "simulation",
        "config": {"mode": "mock"},
    }
    # Existing robot must survive.
    assert "arm_1" in data["robots"]
    # Registered config must still load.
    assert client.get("/api/config").json()["config"]["robots"]["arm_2"]["driver"] == "mock_rover"


def test_api_register_robot_rejects_duplicate_and_bad_id(tmp_path):
    TestClient = _client_or_skip()
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    _prepare_store(config_path)
    client = TestClient(create_app(config_path))
    before = config_path.read_text(encoding="utf-8")

    duplicate = client.post(
        "/api/config/robots", json={"robot_id": "arm_1", "driver": "mock_arm"}
    )
    bad_id = client.post(
        "/api/config/robots", json={"robot_id": "1 bad id!", "driver": "mock_arm"}
    )

    assert duplicate.status_code == 409
    assert bad_id.status_code == 400
    # Nothing may be written on rejection.
    assert config_path.read_text(encoding="utf-8") == before
