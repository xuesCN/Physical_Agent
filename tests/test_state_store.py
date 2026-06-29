import asyncio

import pytest

import physical_agent.agent.chat_runtime as chat_runtime_module
import physical_agent.agent.runtime as agent_runtime_module
import physical_agent.watch.runtime as watch_runtime_module
from physical_agent.agent.chat_runtime import ChatRuntime
from physical_agent.agent.runtime import AgentRuntime
from physical_agent.config import PhysicalAgentConfig, write_default_config
from physical_agent.state import MarkdownStateStore, open_state_store
from physical_agent.state import factory as state_factory
from physical_agent.watch.runtime import WatchRuntime


class _NoSkills:
    def match(self, message):
        return None

    def list_skills(self):
        return []


def test_open_state_store_defaults_to_markdown(tmp_path):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)

    store = open_state_store(config_path=config_path)

    assert isinstance(store, MarkdownStateStore)
    assert store.path == (tmp_path / "workspace").resolve()


def test_open_state_store_rejects_unsupported_backend(tmp_path):
    config = PhysicalAgentConfig.model_validate(
        {"workspace": {"path": "./workspace", "backend": "sqlite"}}
    )

    with pytest.raises(ValueError, match="sqlite.*not implemented"):
        open_state_store(config, base_dir=tmp_path)


def test_core_runtimes_use_state_store_factory(tmp_path, monkeypatch):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    calls = {"agent": 0, "chat": 0, "watch": 0}
    real_open = state_factory.open_state_store

    def spy(name):
        def _open_state_store(*args, **kwargs):
            calls[name] += 1
            return real_open(*args, **kwargs)

        return _open_state_store

    monkeypatch.setattr(agent_runtime_module, "open_state_store", spy("agent"))
    monkeypatch.setattr(chat_runtime_module, "open_state_store", spy("chat"))
    monkeypatch.setattr(watch_runtime_module, "open_state_store", spy("watch"))

    agent = AgentRuntime(config_path)
    asyncio.run(agent.setup())
    assert isinstance(agent.workspace, MarkdownStateStore)

    chat = ChatRuntime(config_path, planner_name="rule_based")
    monkeypatch.setattr(chat, "_skill_router", lambda: _NoSkills())
    result = chat.respond("hello")
    assert result["ok"] is True
    assert isinstance(chat.workspace, MarkdownStateStore)

    watch = WatchRuntime(config_path)
    asyncio.run(watch.setup())
    try:
        assert isinstance(watch.workspace, MarkdownStateStore)
    finally:
        asyncio.run(watch.shutdown())

    assert calls == {"agent": 1, "chat": 1, "watch": 1}
