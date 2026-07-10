from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import Field

from physical_agent.application.plan_compiler import compile_agent_output
from physical_agent.application.ports import PlannerPort
from physical_agent.protocol.actions import (
    ActionCorrelation,
    ProposalContext,
    parse_action_metadata,
    with_proposal_metadata,
)
from physical_agent.protocol.schemas import Action, StrictModel
from physical_agent.protocol.agent_output import AgentOutput
from physical_agent.state import StateStore


ProposalStatus = Literal[
    "waiting_approval",
    "waiting_execution",
    "refused",
    "unavailable",
]


class ProposalResult(StrictModel):
    """Stable result returned by every task-proposal entrypoint."""

    status: ProposalStatus
    task: str
    message: str
    actions: list[Action] = Field(default_factory=list)
    refusal_reason: str | None = None
    correlation: ActionCorrelation
    agent_output: AgentOutput

    @property
    def ok(self) -> bool:
        return bool(self.actions)


class ProposalService:
    """Proposal-only application service.

    It owns the shared task -> planner -> numbered actions -> pending board
    use case. It deliberately has no dependency on watch, drivers, or the
    safety gate; execution remains watch-owned.
    """

    def __init__(
        self,
        store: StateStore,
        planner: PlannerPort | None = None,
        *,
        planner_factory: Callable[[], PlannerPort] | None = None,
    ):
        self.store = store
        self.planner = planner
        self.planner_factory = planner_factory

    def submit_task(
        self,
        task: str,
        *,
        proposed_by: str,
        source: str = "planner",
        owner: str = "human",
        correlation: ActionCorrelation | None = None,
    ) -> ProposalResult:
        normalized_task = task.strip()
        if not normalized_task:
            raise ValueError("Task cannot be empty.")

        correlation = correlation or ActionCorrelation.create()
        self.store.write_task(normalized_task, owner=owner)
        capabilities = self.store.read_capabilities()
        robots = capabilities.get("robots") if isinstance(capabilities, dict) else None
        if not isinstance(robots, dict) or not robots:
            message = "No capabilities are available yet. Start `physical-agent watch` first."
            refusal_reason = "No live robot capabilities are available."
            return ProposalResult(
                status="unavailable",
                task=normalized_task,
                message=message,
                refusal_reason=refusal_reason,
                correlation=correlation,
                agent_output=compile_agent_output(
                    [],
                    status="unavailable",
                    decision="wait",
                    lifecycle="submitted",
                    message=message,
                    proposal_id=correlation.proposal_id,
                    refusal_reason=refusal_reason,
                ),
            )

        planner = self.planner
        if planner is None and self.planner_factory is not None:
            planner = self.planner_factory()
        if planner is None:
            raise RuntimeError("Task proposals require a configured planner.")
        world = self.store.read_world()
        contextual_plan = getattr(planner, "plan_with_context", None)
        if callable(contextual_plan):
            plan_document = self.store.read_plan()
            plan_value = plan_document.get("plan")
            previous_agent_output = getattr(plan_value, "agent_output", None)
            actions = contextual_plan(
                task=normalized_task,
                capabilities=capabilities,
                world=world,
                feedback=self.store.read_feedback(),
                safety=self.store.read_safety(),
                previous_agent_output=previous_agent_output,
            )
        else:
            actions = planner.plan(
                task=normalized_task,
                capabilities=capabilities,
                world=world,
            )
        refusal_reason = _planner_refusal_reason(planner)
        if not actions:
            message = "No action could be planned for this task."
            reason = (
                refusal_reason
                or "No supported robot capability matched the submitted task."
            )
            return ProposalResult(
                status="refused",
                task=normalized_task,
                message=message,
                refusal_reason=reason,
                correlation=correlation,
                agent_output=compile_agent_output(
                    [],
                    status="refused",
                    decision="refuse",
                    lifecycle="submitted",
                    message=message,
                    proposal_id=correlation.proposal_id,
                    refusal_reason=reason,
                ),
            )

        numbered = renumber_actions(actions, self.store)
        _validate_external_dependencies(numbered, self.store)
        _validate_compilable_graph(numbered)
        proposed: list[Action] = []
        for action in numbered:
            context = ProposalContext(
                source=source,
                proposed_by=proposed_by,
                original_task=normalized_task,
                planner_reason=action.reason,
                correlation=correlation,
            )
            proposed.append(with_proposal_metadata(action, context))
        appended = self.store.append_pending_actions(proposed)

        waiting_approval = any(
            (action.metadata.get("approval") or {}).get("status") == "pending"
            for action in appended
        )
        status: ProposalStatus = (
            "waiting_approval" if waiting_approval else "waiting_execution"
        )
        message = (
            "Actions are queued and waiting for execution approval."
            if waiting_approval
            else "Actions are queued; watch must validate them before execution."
        )
        return ProposalResult(
            status=status,
            task=normalized_task,
            message=message,
            actions=appended,
            refusal_reason=refusal_reason,
            correlation=correlation,
            agent_output=compile_agent_output(
                appended,
                status=status,
                decision="propose",
                lifecycle="submitted",
                message=message,
                proposal_id=correlation.proposal_id,
                refusal_reason=refusal_reason,
            ),
        )

    def propose_action(
        self,
        action: Action | dict,
        *,
        proposed_by: str,
        source: str,
        correlation: ActionCorrelation | None = None,
        user_message: str | None = None,
        draft_reason: str | None = None,
    ) -> Action:
        parsed = action if isinstance(action, Action) else Action.model_validate(action)
        _validate_external_dependencies([parsed], self.store)
        _validate_compilable_graph([parsed])
        context = ProposalContext(
            source=source,
            proposed_by=proposed_by,
            user_message=user_message,
            draft_reason=draft_reason,
            correlation=correlation or ActionCorrelation.create(),
        )
        return self.store.append_pending_action(with_proposal_metadata(parsed, context))

    def propose_action_result(
        self,
        action: Action | dict,
        *,
        proposed_by: str,
        source: str,
        correlation: ActionCorrelation | None = None,
        user_message: str | None = None,
        draft_reason: str | None = None,
    ) -> ProposalResult:
        """Append one intent and return the same compiled contract as submit_task.

        ``propose_action`` remains as the narrow compatibility method for
        callers that only need the appended Action. New adapters should use
        this result method so status/correlation/AgentOutput cannot drift.
        """

        correlation = correlation or ActionCorrelation.create()
        appended = self.propose_action(
            action,
            proposed_by=proposed_by,
            source=source,
            correlation=correlation,
            user_message=user_message,
            draft_reason=draft_reason,
        )
        metadata = parse_action_metadata(appended.metadata)
        waiting_approval = bool(
            metadata.approval is not None
            and metadata.approval.status == "pending"
        )
        status: ProposalStatus = (
            "waiting_approval" if waiting_approval else "waiting_execution"
        )
        message = (
            "Action is waiting for execution approval."
            if waiting_approval
            else "Action is queued; watch must validate it before execution."
        )
        task = (
            (user_message or draft_reason or appended.reason or appended.id).strip()
        )
        return ProposalResult(
            status=status,
            task=task,
            message=message,
            actions=[appended],
            correlation=correlation,
            agent_output=compile_agent_output(
                [appended],
                status=status,
                decision="propose",
                lifecycle="submitted",
                message=message,
                proposal_id=correlation.proposal_id,
            ),
        )


def renumber_actions(actions: list[Action], store: StateStore) -> list[Action]:
    start = _max_action_number(_known_action_ids(store)) + 1
    old_to_new: dict[str, str] = {}
    items: list[dict] = []
    for offset, action in enumerate(actions):
        data = action.model_dump(mode="json")
        old_id = str(data["id"])
        new_id = f"act_{start + offset:03d}"
        old_to_new[old_id] = new_id
        data["id"] = new_id
        items.append(data)

    result: list[Action] = []
    for data in items:
        data["depends_on"] = [
            old_to_new.get(str(dependency), str(dependency))
            for dependency in data.get("depends_on", [])
        ]
        result.append(Action.model_validate(data))
    return result


def _known_action_ids(store: StateStore) -> set[str]:
    action_board = store.read_actions()
    ids = {
        action.id
        for action in (
            action_board["pending"]
            + action_board.get("in_progress", [])
            + action_board["completed"]
            + action_board["cancelled"]
        )
    }
    for item in store.read_feedback().get("history", []):
        action_id = item.get("action_id") if isinstance(item, dict) else None
        if action_id:
            ids.add(str(action_id))
    return ids


def _max_action_number(action_ids: set[str]) -> int:
    maximum = 0
    for action_id in action_ids:
        if not action_id.startswith("act_"):
            continue
        try:
            maximum = max(maximum, int(action_id.removeprefix("act_")))
        except ValueError:
            continue
    return maximum


def _planner_refusal_reason(planner: PlannerPort) -> str | None:
    value = getattr(planner, "last_refusal_reason", None)
    return str(value) if value else None


def _validate_compilable_graph(actions: list[Action]) -> None:
    """Fail before state mutation if intents cannot form a valid task DAG."""

    compile_agent_output(
        actions,
        status="draft",
        decision="propose",
        lifecycle="draft",
        message="Validate proposal task graph.",
    )


def _validate_external_dependencies(actions: list[Action], store: StateStore) -> None:
    batch_ids = {action.id for action in actions}
    board = store.read_actions()
    statuses: dict[str, str] = {}
    for status in ("pending", "in_progress", "completed", "cancelled"):
        for existing in board.get(status, []):
            statuses[existing.id] = status
    for action in actions:
        if action.id in statuses:
            raise ValueError(f"Action id already exists: {action.id}")
    for action in actions:
        for dependency in action.depends_on:
            if dependency in batch_ids:
                continue
            status = statuses.get(dependency)
            if status is None:
                raise ValueError(
                    f"Action {action.id} references unknown dependency: {dependency}"
                )
            if status == "cancelled":
                raise ValueError(
                    f"Action {action.id} depends on cancelled action: {dependency}"
                )
