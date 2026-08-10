from __future__ import annotations

from pathlib import Path
from typing import Any

from physical_agent.agent.context_builder import (
    DEFAULT_CONTEXT_BUDGET,
    ContextBudget,
    build_planner_context,
)
from physical_agent.agent.llm_contracts import ACTION_PLAN_SCHEMA, PlannerLLMResponse
from physical_agent.agent.planner import Planner
from physical_agent.agent.rule_based import RuleBasedPlanner
from physical_agent.llm import (
    OpenAICompatibleClient,
    OpenAICompatibleSettings,
    ProviderRefusalError,
)
from physical_agent.protocol.schemas import Action


class LLMPlanner(Planner):
    def __init__(
        self,
        *,
        settings: OpenAICompatibleSettings | None = None,
        env_file: str = ".env",
        model: str | None = None,
        workspace_path: str | Path | None = None,
        context_budget: ContextBudget = DEFAULT_CONTEXT_BUDGET,
    ):
        self.settings = settings or OpenAICompatibleSettings.from_env(
            env_file=env_file,
            model=model,
            workspace_path=workspace_path,
        )
        self.client = OpenAICompatibleClient(self.settings)
        self.fallback = RuleBasedPlanner()
        self.last_refusal_reason: str | None = None
        self.context_budget = context_budget

    def plan(
        self,
        *,
        task: str,
        capabilities: dict[str, Any],
        world: dict[str, Any],
    ) -> list[Action]:
        return self.plan_with_context(
            task=task,
            capabilities=capabilities,
            world=world,
        )

    def plan_with_context(
        self,
        *,
        task: str,
        capabilities: dict[str, Any],
        world: dict[str, Any],
        feedback: dict[str, Any] | None = None,
        safety: dict[str, Any] | None = None,
        previous_agent_output: dict[str, Any] | None = None,
    ) -> list[Action]:
        context = build_planner_context(
            task,
            capabilities=capabilities,
            world=world,
            feedback=feedback,
            safety=safety,
            previous_agent_output=previous_agent_output,
            budget=self.context_budget,
        )
        try:
            payload = self.client.structured_json(
                context.messages,
                schema=ACTION_PLAN_SCHEMA,
                schema_name="physical_action_plan",
                response_model=PlannerLLMResponse,
                temperature=context.temperature,
                max_tokens=context.max_tokens,
                metadata={"physical_agent_surface": "planner"},
                max_validation_retries=1,
            )
        except ProviderRefusalError as exc:
            self.last_refusal_reason = exc.refusal
            return []
        actions_data = payload.get("actions", [])
        refusal_reason = payload.get("refusal_reason")
        self.last_refusal_reason = str(refusal_reason) if refusal_reason else None
        if not isinstance(actions_data, list):
            raise ValueError("LLM planner response must contain an actions list.")
        normalized_items: list[dict[str, Any]] = []
        for index, item in enumerate(actions_data, start=1):
            if not isinstance(item, dict):
                raise ValueError("Each LLM planner action must be an object.")
            item = dict(item)
            item["id"] = str(item.get("id") or f"act_{index:03d}")
            item.setdefault("params", {})
            normalized_items.append(item)

        action_ids = [item["id"] for item in normalized_items]
        actions = []
        for index, item in enumerate(normalized_items):
            item["depends_on"] = _normalize_depends_on(
                item.get("depends_on", []),
                action_ids,
                current_index=index,
            )
            actions.append(Action.model_validate(item))
        return actions
def _normalize_depends_on(
    value: Any,
    action_ids: list[str],
    *,
    current_index: int | None = None,
) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        value = [value]
    dependencies: list[str] = []
    for dependency in value:
        if dependency is False:
            continue
        if isinstance(dependency, int):
            if dependency == 0 and action_ids:
                dependencies.append(action_ids[0])
                continue
            if 1 <= dependency <= len(action_ids):
                dependencies.append(action_ids[dependency - 1])
                continue
        text = str(dependency)
        if text.isdigit():
            number = int(text)
            if number == 0 and action_ids:
                dependencies.append(action_ids[0])
                continue
            if 1 <= number <= len(action_ids):
                dependencies.append(action_ids[number - 1])
                continue
        if text.lower() in {"none", "null", "false", "no", "n/a"}:
            continue
        if text in action_ids or text.startswith("act_"):
            dependencies.append(text)
            continue
        if current_index is not None and current_index > 0:
            dependencies.append(action_ids[current_index - 1])
            continue
        if action_ids:
            dependencies.append(action_ids[0])
    return dependencies
