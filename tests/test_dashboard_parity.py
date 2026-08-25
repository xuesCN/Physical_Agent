from __future__ import annotations

import json

import pytest
import yaml

import physical_agent.agent.driver_coder as driver_coder_module
from physical_agent.api.server import create_app
from physical_agent.llm import OpenAICompatibleSettings
from physical_agent.quickstart import setup_project


def _test_client():
    pytest.importorskip("fastapi")
    try:
        from fastapi.testclient import TestClient
    except (ImportError, RuntimeError) as exc:
        pytest.skip(f"fastapi.testclient is unavailable; install .[dev,server]: {exc}")
    return TestClient


def test_fastapi_integrate_llm_preserves_model_override_and_generated_result(
    tmp_path,
    monkeypatch,
):
    sdk = tmp_path / "vendor_sdk"
    sdk.mkdir()
    (sdk / "README.md").write_text(
        "# Dashboard parity device\n\nPython SDK with observe support.",
        encoding="utf-8",
    )
    config_path = tmp_path / "physical-agent.yaml"
    setup_project(config_path, publish=False)
    captured: dict[str, str | None] = {}

    def fake_from_env(cls, **kwargs):
        model = kwargs.get("model")
        captured["from_env_model"] = model
        return cls(
            api_key="test-key",
            base_url="http://local-llm.test/v1",
            model=str(model or "default-model"),
        )

    class FakeClient:
        def __init__(self, settings):
            captured["client_model"] = settings.model

        def chat(self, messages, **kwargs):
            request = json.loads(messages[-1]["content"])
            original = request["existing_scaffold"]["driver.py"]
            return json.dumps(
                {
                    "summary": "Generated through the canonical FastAPI path.",
                    "files": [
                        {
                            "path": "driver.py",
                            "content": original + "\n# dashboard-parity-generated\n",
                        }
                    ],
                    "next_steps": ["Connect the real SDK behind driver.execute."],
                    "tests": ["Load the generated driver in mock mode."],
                }
            )

    monkeypatch.setattr(
        OpenAICompatibleSettings,
        "from_env",
        classmethod(fake_from_env),
    )
    monkeypatch.setattr(driver_coder_module, "OpenAICompatibleClient", FakeClient)

    client = _test_client()(create_app(config_path))
    response = client.post(
        "/api/integrate",
        json={
            "source": str(sdk),
            "name": "dashboard_driver",
            "llm": True,
            "model": "override-model",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["result"]["llm_used"] is True
    assert body["result"]["summary"] == "Generated through the canonical FastAPI path."
    assert captured == {
        "from_env_model": "override-model",
        "client_model": "override-model",
    }
    output_path = tmp_path / "physical-agent-integration" / "dashboard_driver"
    assert "dashboard-parity-generated" in (output_path / "driver.py").read_text(
        encoding="utf-8"
    )


def test_effective_config_exposes_execution_mode_without_running_watch(tmp_path):
    config_path = tmp_path / "physical-agent.yaml"
    setup_project(config_path, publish=False)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["robots"]["arm_1"]["execution_mode"] = "simulation"
    data["robots"]["hardware_arm"] = {
        "driver": "xiaozhi_mcp",
        "execution_mode": "hardware",
        "config": {},
    }
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    client = _test_client()(create_app(config_path, enable_watch=False))
    response = client.get("/api/config")

    assert response.status_code == 200
    robots = response.json()["config"]["robots"]
    assert robots["arm_1"]["execution_mode"] == "simulation"
    assert robots["hardware_arm"]["execution_mode"] == "hardware"
    assert client.get("/api/health").json()["executor"]["mode"] == "none"


def test_canonical_dashboard_does_not_restore_legacy_execution_controls(tmp_path):
    config_path = tmp_path / "physical-agent.yaml"
    setup_project(config_path, publish=False)
    client = _test_client()(create_app(config_path, enable_watch=False))

    for path in (
        "/api/setup",
        "/api/demo",
        "/api/watch/start",
        "/api/watch/stop",
        "/api/watch/step",
    ):
        assert client.post(path, json={}).status_code == 404
    assert client.get("/api/doctor").status_code == 404
