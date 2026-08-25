from __future__ import annotations

from pathlib import Path

from physical_agent.config import load_config


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "moce_arm"


def test_partial_hardware_example_uses_a_clean_sqlite_workspace() -> None:
    config = load_config(EXAMPLE / "physical-agent.partial-hardware.yaml")

    assert config.workspace.backend == "sqlite"
    assert config.workspace.path == "./workspace-partial-hardware"
    workspace = EXAMPLE / config.workspace.path
    retired_runtime_documents = {
        "TASK.md",
        "CAPABILITIES.md",
        "WORLD.md",
        "ACTIONS.md",
        "FEEDBACK.md",
        "CHAT.md",
        "PLAN.md",
        "MEMORY.md",
    }
    assert not any((workspace / name).exists() for name in retired_runtime_documents)
    retired_workspace = EXAMPLE / "workspace-partial-wrist-gripper"
    assert not retired_workspace.exists() or not any(retired_workspace.iterdir())
