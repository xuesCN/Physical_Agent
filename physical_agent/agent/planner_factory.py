from __future__ import annotations

from pathlib import Path

from physical_agent.agent.llm_planner import LLMPlanner
from physical_agent.agent.planner import Planner
from physical_agent.agent.rule_based import RuleBasedPlanner
from physical_agent.config import PhysicalAgentConfig


def create_planner(
    config: PhysicalAgentConfig,
    *,
    base_dir: str | Path,
    planner_name: str | None = None,
    model: str | None = None,
) -> Planner:
    """Resolve the configured planner consistently for every entrypoint."""

    root = Path(base_dir).resolve()
    name = (planner_name or config.agent.planner or "rule_based").lower()
    if name in {"rule_based", "rules", "offline"}:
        return RuleBasedPlanner()
    if name in {"llm", "openai", "openai_compatible", "openai-compatible"}:
        selected_model = model
        if selected_model is None and config.agent.model != "fake/local":
            selected_model = config.agent.model
        return LLMPlanner(
            env_file=str(root / ".env"),
            model=selected_model,
            workspace_path=config.workspace_path(root),
        )
    raise ValueError(f"Unsupported planner: {name}")
