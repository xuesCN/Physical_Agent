from __future__ import annotations

from pathlib import Path

import pytest
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
from physical_agent.llm import OpenAICompatibleError, llm_settings_path
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
    assert proposed["action"]["id"] == "act_controller_direct"

    submitted = controller.submit_task(
        SubmitTaskRequest(task="pick the red block and place it on the tray")
    )
    assert [item["capability"] for item in submitted["actions"]] == ["pick", "place"]

    chat = controller.chat(ChatRequest(message="remember that controller memory is safe"))
    assert chat["executed"] == 0
    assert chat["memory"][0]["content"] == "controller memory is safe"

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
    assert proposed.json()["action"]["id"] == "act_api_direct"

    submitted = client.post(
        "/api/tasks/submit",
        json={"task": "pick the red block and place it on the tray"},
    )
    assert submitted.status_code == 200
    assert [item["capability"] for item in submitted.json()["actions"]] == ["pick", "place"]
    assert [item["id"] for item in submitted.json()["actions"]] == ["act_001", "act_002"]
    assert submitted.json()["actions"][1]["depends_on"] == ["act_001"]

    chat = client.post("/api/chat", json={"message": "remember that API memory is safe"})
    assert chat.status_code == 200
    assert chat.json()["executed"] == 0
    assert "I will remember" in chat.json()["reply"]
    assert chat.json()["memory"][0]["content"] == "API memory is safe"

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
        },
    )
    assert saved.status_code == 200
    assert saved.json()["has_api_key"] is True
    assert saved.json()["masked_api_key"] == "****7890"
    assert "sk-local-secret-7890" not in saved.text

    settings_file = llm_settings_path(tmp_path / "workspace")
    assert settings_file.exists()
    assert "sk-local-secret-7890" in settings_file.read_text(encoding="utf-8")

    fetched = client.get("/api/settings/llm")
    assert fetched.status_code == 200
    assert fetched.json()["base_url"] == "http://local-llm.test/v1"
    assert fetched.json()["model"] == "local-model"
    assert fetched.json()["api_mode"] == "chat_completions"
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
    assert body["executed"] == 0
    messages = body["state"]["chat"]["messages"]
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "hello from API"


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
        def respond(self, message, *, auto_step=False):
            calls["respond"] = {"message": message, "auto_step": auto_step}
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
    response = client.post("/api/chat", json={"message": "hello", "auto_step": True})

    assert response.status_code == 200
    assert calls["runtime"] == {
        "config": config_path.resolve(),
        "planner_name": "auto",
        "enable_code_skills": False,
        "enable_hardware_integration": False,
    }
    assert calls["respond"] == {"message": "hello", "auto_step": False}


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
        json={"message": "look around", "auto_step": True},
    ).status_code == 200
    assert client.post(
        "/api/upload",
        files={"file": ("safe.md", b"upload text remains untrusted", "text/markdown")},
    ).status_code == 200

    store = open_state_store(config_path=config_path)
    assert [item.id for item in store.read_actions()["completed"]] == []
    assert [item.id for item in store.read_actions()["cancelled"]] == []
