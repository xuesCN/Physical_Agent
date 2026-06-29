from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import yaml

from physical_agent.agent.chat_runtime import ChatRuntime
from physical_agent.agent.tool_loop import OpenAIToolLoop, ToolLoopError
from physical_agent.config import write_default_config
from physical_agent.drivers.mock_arm import MockArmDriver
from physical_agent.llm import OpenAICompatibleSettings
from physical_agent.protocol.schemas import Action
from physical_agent.protocol.workspace import Workspace
from physical_agent.quickstart import setup_project
from physical_agent.state import open_state_store


class _SequenceHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []
    responses: list[dict] = []

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        self.__class__.requests.append(payload)
        response = self.__class__.responses.pop(0)
        body = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return


def _server(responses: list[dict]):
    _SequenceHandler.requests = []
    _SequenceHandler.responses = list(responses)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SequenceHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_tool_loop_chat_completions_proposes_action_only(tmp_path):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    workspace = Workspace(tmp_path / "workspace")
    workspace.initialize()
    server = _server(
        [
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "physical_agent_propose_action",
                                        "arguments": json.dumps(
                                            {
                                                "id": "act_tool_001",
                                                "robot": "arm_1",
                                                "capability": "observe",
                                                "params": {},
                                                "reason": "Inspect current state.",
                                            }
                                        ),
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
            {"choices": [{"message": {"role": "assistant", "content": "Proposed safely."}}]},
        ]
    )
    try:
        settings = OpenAICompatibleSettings(
            api_key="test-key",
            base_url=f"http://127.0.0.1:{server.server_address[1]}/v1",
            model="test-model",
        )
        result = asyncio.run(
            OpenAIToolLoop(config_path, settings=settings).run(
                [
                    {"role": "system", "content": "Use tools for Physical Agent proposals."},
                    {"role": "user", "content": "look around"},
                ],
                metadata={"physical_agent_surface": "tool_loop_test"},
            )
        )

        assert result.content == "Proposed safely."
        assert [step.name for step in result.steps] == ["physical_agent_propose_action"]
        actions = workspace.read_actions()
        assert [action.id for action in actions["pending"]] == ["act_tool_001"]
        assert actions["completed"] == []
        first_request = _SequenceHandler.requests[0]
        assert first_request["tools"][0]["type"] == "function"
        assert "function" in first_request["tools"][0]
        assert first_request["metadata"]["physical_agent_surface"] == "tool_loop_test"
        second_request = _SequenceHandler.requests[1]
        assert second_request["messages"][-1]["role"] == "tool"
        assert second_request["messages"][-1]["tool_call_id"] == "call_1"
    finally:
        server.shutdown()
        server.server_close()


def test_tool_loop_chat_completions_proposes_action_only_sqlite(tmp_path):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["workspace"]["backend"] = "sqlite"
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    store = open_state_store(config_path=config_path)
    store.initialize()
    server = _server(
        [
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "physical_agent_propose_action",
                                        "arguments": json.dumps(
                                            {
                                                "id": "act_sqlite_001",
                                                "robot": "arm_1",
                                                "capability": "observe",
                                                "params": {},
                                                "reason": "Inspect current state.",
                                            }
                                        ),
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
            {"choices": [{"message": {"role": "assistant", "content": "Proposed safely."}}]},
        ]
    )
    try:
        settings = OpenAICompatibleSettings(
            api_key="test-key",
            base_url=f"http://127.0.0.1:{server.server_address[1]}/v1",
            model="test-model",
        )
        result = asyncio.run(
            OpenAIToolLoop(config_path, settings=settings).run(
                [
                    {"role": "system", "content": "Use tools for Physical Agent proposals."},
                    {"role": "user", "content": "look around"},
                ],
                metadata={"physical_agent_surface": "tool_loop_sqlite_test"},
            )
        )

        assert result.content == "Proposed safely."
        assert [step.name for step in result.steps] == ["physical_agent_propose_action"]
        actions = store.read_actions()
        assert [action.id for action in actions["pending"]] == ["act_sqlite_001"]
        assert actions["completed"] == []
        assert actions["cancelled"] == []
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("planner_name", ["tool_loop", "openai_tool_loop"])
def test_chat_runtime_tool_loop_submit_task_writes_pending_only(
    tmp_path,
    monkeypatch,
    planner_name,
):
    config_path = tmp_path / "physical-agent.yaml"
    setup_project(config_path, publish=True)
    workspace = Workspace(tmp_path / "workspace")
    completed = Action(
        id="act_005",
        robot="arm_1",
        capability="observe",
        params={},
        reason="Already completed.",
    )
    cancelled = Action(
        id="act_006",
        robot="arm_1",
        capability="observe",
        params={},
        reason="Already cancelled.",
    )
    workspace.write_actions([], [completed], [cancelled])
    workspace.write_chat(
        [{"role": "user", "content": "old recent message"}],
        running_summary="Old tool summary mentions unsafe_execute and stale world.",
        compact=False,
    )

    async def fail_execute(self, action):
        raise AssertionError("driver.execute must not be called by tool_loop submit_task")

    monkeypatch.setattr(MockArmDriver, "execute", fail_execute)
    server = _server(
        [
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_submit",
                                    "type": "function",
                                    "function": {
                                        "name": "physical_agent_submit_task",
                                        "arguments": json.dumps({"task": "look around"}),
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
            {"choices": [{"message": {"role": "assistant", "content": "Task proposed safely."}}]},
        ]
    )
    try:
        (tmp_path / ".env").write_text(
            f"GPT_URL=http://127.0.0.1:{server.server_address[1]}/v1\n"
            "GPT_KEY=test-key\n"
            "GPT_MODEL=test-model\n",
            encoding="utf-8",
        )

        result = ChatRuntime(config_path, planner_name=planner_name).respond("look around")

        assert result["ok"] is True
        assert result["mode"] == "tool_loop"
        assert result["reply"] == "Task proposed safely."
        assert [step["name"] for step in result["tool_steps"]] == [
            "physical_agent_submit_task"
        ]
        assert [action["capability"] for action in result["actions"]] == ["observe"]
        actions = workspace.read_actions()
        assert [action.id for action in actions["pending"]] == ["act_007"]
        assert [action.id for action in actions["completed"]] == ["act_005"]
        assert [action.id for action in actions["cancelled"]] == ["act_006"]
        assert actions["pending"][0].capability == "observe"
        context = json.loads(_SequenceHandler.requests[0]["messages"][1]["content"])
        assert context["running_summary"] == (
            "Old tool summary mentions unsafe_execute and stale world."
        )
        assert context["chat_history"][-1]["content"] == "look around"
        assert context["capabilities"]["robots"]["arm_1"]["capabilities"][0]["name"] == "observe"
        assert "unsafe_execute" not in json.dumps(context["capabilities"])
        assert _SequenceHandler.requests[0]["tools"][0]["function"]["name"] == (
            "physical_agent_submit_task"
        )
        assert _SequenceHandler.requests[1]["messages"][-1]["role"] == "tool"
    finally:
        server.shutdown()
        server.server_close()


def test_tool_loop_responses_api_round_trips_function_output(tmp_path):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    workspace = Workspace(tmp_path / "workspace")
    workspace.initialize()
    server = _server(
        [
            {
                "output": [
                    {
                        "type": "function_call",
                        "id": "fc_1",
                        "call_id": "call_1",
                        "name": "physical_agent_get_state",
                        "arguments": "{}",
                    }
                ]
            },
            {
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "State read."}],
                    }
                ]
            },
        ]
    )
    try:
        settings = OpenAICompatibleSettings(
            api_key="test-key",
            base_url=f"http://127.0.0.1:{server.server_address[1]}/v1",
            model="test-model",
            api_mode="responses",
        )
        result = asyncio.run(
            OpenAIToolLoop(config_path, settings=settings).run(
                [
                    {"role": "system", "content": "Use proposal-only tools."},
                    {"role": "user", "content": "what is the state?"},
                ]
            )
        )

        assert result.content == "State read."
        assert result.steps[0].name == "physical_agent_get_state"
        first_request = _SequenceHandler.requests[0]
        assert first_request["tools"][0]["name"].startswith("physical_agent_")
        second_request = _SequenceHandler.requests[1]
        assert any(
            item.get("type") == "function_call_output" and item.get("call_id") == "call_1"
            for item in second_request["input"]
        )
    finally:
        server.shutdown()
        server.server_close()


def test_tool_loop_rejects_non_allowlisted_tool(tmp_path):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    workspace = Workspace(tmp_path / "workspace")
    workspace.initialize()
    server = _server(
        [
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "physical_agent_driver_execute",
                                        "arguments": "{}",
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    )
    try:
        settings = OpenAICompatibleSettings(
            api_key="test-key",
            base_url=f"http://127.0.0.1:{server.server_address[1]}/v1",
            model="test-model",
        )
        with pytest.raises(ToolLoopError, match="not allowlisted"):
            asyncio.run(OpenAIToolLoop(config_path, settings=settings).run([]))

        assert workspace.read_actions()["pending"] == []
    finally:
        server.shutdown()
        server.server_close()
