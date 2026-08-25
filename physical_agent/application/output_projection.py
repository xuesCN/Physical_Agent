from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from physical_agent.application.plan_compiler import compile_agent_output
from physical_agent.protocol.agent_output import (
    AgentOutput,
    AgentOutputStatus,
    AgentTask,
    safety_gate_task_id,
)
from physical_agent.protocol.schemas import Action, ChatPlan


def materialize_agent_output(
    output: AgentOutput,
    *,
    actions: dict[str, Any],
    feedback: dict[str, Any],
    claim_owners: Mapping[str, str] | None = None,
) -> AgentOutput:
    """Project board and feedback facts onto an immutable compiled graph.

    The compiled graph remains the source of task topology. Runtime state is
    owned by the Action board and watch feedback until a persistent obligation
    engine is introduced.
    """

    if output.lifecycle == "draft":
        return output

    action_states = _action_states(actions)
    action_values = _action_values(actions)
    events = _feedback_events(feedback)
    latest_gate = _latest_events(events, "safety_gate")
    latest_verification = _latest_events(events, "expectation_check")
    tasks: list[AgentTask] = []

    for task in output.tasks:
        action = action_values.get(task.action_id)
        action_state = action_states.get(task.action_id)
        raw_gate_event = latest_gate.get(task.action_id)
        raw_gate_is_canonical = _is_authoritative_gate_event(
            raw_gate_event,
            task.action_id,
        )
        gate_event = (
            raw_gate_event
            if raw_gate_is_canonical
            else None
        )
        stored_claim_owner = (
            str(claim_owners.get(task.action_id) or "") or None
            if claim_owners is not None
            else None
        )
        terminal_result_owner = (
            _preclaim_dependency_rejection_owner(
                events,
                action_id=task.action_id,
                gate_event=raw_gate_event,
            )
            if action_state == "cancelled" and stored_claim_owner is None
            else None
        )
        current_claim_owner = stored_claim_owner or terminal_result_owner
        terminal_claim_owner_required = action_state == "completed" or (
            action_state == "cancelled" and _approval_status(action) != "rejected"
        )
        claim_owner_missing = current_claim_owner is None and (
            action_state == "in_progress"
            or (claim_owners is not None and terminal_claim_owner_required)
        )
        if gate_event is not None and action_state in {
            "in_progress",
            "completed",
            "cancelled",
        }:
            if current_claim_owner is None:
                if action_state == "in_progress" or claim_owners is not None:
                    gate_event = None
            else:
                if str(gate_event.get("executor_id") or "") != current_claim_owner:
                    raw_gate_event = _latest_gate_event_for_owner(
                        events,
                        action_id=task.action_id,
                        executor_id=current_claim_owner,
                    )
                    raw_gate_is_canonical = _is_authoritative_gate_event(
                        raw_gate_event,
                        task.action_id,
                    )
                    gate_event = (
                        raw_gate_event if raw_gate_is_canonical else None
                    )
                if raw_gate_event is None:
                    # A recovered action can be claimed by a successor while
                    # the prior owner's canonical Gate event remains in
                    # feedback. The event is stale for this claim, not forged
                    # evidence.
                    gate_event = None
        if (
            action_state == "pending"
            and gate_event is not None
            and gate_event.get("status") == "passed"
            and gate_event.get("decision") == "allow"
        ):
            # A claimed action may be recovered to pending after the executor
            # disappears. Its next claim must run SafetyGate again, so a passed
            # decision from the abandoned claim cannot satisfy the current
            # public obligation. Invalid evidence is intentionally not cleared
            # here and still fails closed below.
            raw_gate_event = None
            gate_event = None
        verification_event = latest_verification.get(task.action_id)
        status = task.status
        details = dict(task.details)

        if task.kind == "approval":
            approval_status = _approval_status(action)
            if approval_status == "approved":
                status = "completed"
            elif approval_status == "rejected":
                status = "rejected"
            elif approval_status == "pending":
                status = "requested"

        elif task.kind == "safety_gate":
            if raw_gate_event is not None and not raw_gate_is_canonical:
                status = "failed"
                details["projection_error"] = {
                    "code": "safety.gate.evidence_invalid",
                    "message": (
                        "SafetyGate feedback is not a canonical watch-owned "
                        "decision and cannot satisfy the mandatory task."
                    ),
                }
            elif claim_owner_missing:
                status = "failed"
                error_code = (
                    "safety.gate.claim_owner_missing"
                    if action_state == "in_progress"
                    else "safety.gate.final_claim_owner_missing"
                )
                error_message = (
                    "In-progress action has no current claim owner, so "
                    "SafetyGate evidence cannot satisfy the mandatory task."
                    if action_state == "in_progress"
                    else "Terminal action has no final claim owner, so "
                    "SafetyGate evidence cannot satisfy the mandatory task."
                )
                details["projection_error"] = {
                    "code": error_code,
                    "message": error_message,
                }
            elif gate_event is not None:
                gate_status = str(gate_event.get("status") or "")
                status = (
                    "passed"
                    if gate_status == "passed"
                    else "rejected"
                    if gate_status == "rejected"
                    else "failed"
                )
                details["last_decision"] = gate_event
            elif action_state == "completed":
                # A completed board row without the watch-owned Gate decision
                # is an assurance invariant breach. Preserve completion as the
                # physical fact below, but fail the compiled obligation rather
                # than manufacturing a successful Gate result.
                status = "failed"
                details["projection_error"] = {
                    "code": "safety.gate.evidence_missing",
                    "message": (
                        "Action is completed but no mandatory SafetyGate "
                        "decision was recorded."
                    ),
                }
            elif _approval_status(action) == "rejected":
                status = "skipped"
            elif action_state == "in_progress":
                status = "checking"

        elif task.kind == "physical_action":
            gate_status = str((gate_event or {}).get("status") or "")
            if gate_status == "rejected" or _approval_status(action) == "rejected":
                status = "skipped"
            elif action_state == "completed":
                status = "completed"
            elif action_state == "cancelled":
                status = "failed"
            elif action_state == "in_progress" and gate_status == "passed":
                status = "checking"

        elif task.kind == "verification":
            if verification_event is not None:
                verification_status = str(
                    verification_event.get("status") or ""
                )
                status = {
                    "verified": "passed",
                    "violated": "failed",
                    "skipped": "skipped",
                }.get(verification_status, "failed")
                details["last_result"] = verification_event
            else:
                physical_status = _physical_status_for_action(
                    action_state,
                    gate_event=gate_event,
                    approval_status=_approval_status(action),
                )
                if physical_status in {"failed", "skipped"}:
                    status = "skipped"
                elif physical_status == "completed":
                    status = "checking"

        tasks.append(task.model_copy(update={"status": status, "details": details}))

    return output.model_copy(
        update={
            "tasks": tasks,
            "status": _output_status(output, tasks),
        }
    )


def current_agent_output(
    *,
    actions: dict[str, Any],
    feedback: dict[str, Any],
    claim_owners: Mapping[str, str] | None = None,
    preferred: AgentOutput | dict[str, Any] | None = None,
) -> AgentOutput | None:
    """Return a current projection, rebuilding all active submitted tasks.

    This prevents a later chat-only plan from hiding still-pending physical
    obligations. The singleton ChatPlan is presentation state, not task truth.
    """

    preferred_output = _coerce_output(preferred)
    if preferred_output is not None and preferred_output.lifecycle == "draft":
        if not _active_actions(actions):
            return preferred_output

    board_values = _action_values(actions)
    selected: list[Action] = []
    selected_ids: set[str] = set()
    for action in _active_actions(actions):
        if action.id not in selected_ids:
            selected.append(action)
            selected_ids.add(action.id)

    if preferred_output is not None and preferred_output.lifecycle == "submitted":
        for planned_action in preferred_output.actions:
            current = board_values.get(planned_action.id, planned_action)
            if current.id not in selected_ids:
                selected.append(current)
                selected_ids.add(current.id)

    if not selected:
        return (
            materialize_agent_output(
                preferred_output,
                actions=actions,
                feedback=feedback,
                claim_owners=claim_owners,
            )
            if preferred_output is not None
            else None
        )

    proposal_ids = {
        proposal_id
        for action in selected
        if (proposal_id := _proposal_id(action)) is not None
    }
    waiting_approval = any(
        _approval_status(action) == "pending" for action in selected
    )
    preferred_action_ids = (
        {action.id for action in preferred_output.actions}
        if preferred_output is not None
        else set()
    )
    preferred_describes_selection = bool(
        preferred_action_ids & {action.id for action in selected}
    )
    compiled = compile_agent_output(
        selected,
        status="waiting_approval" if waiting_approval else "waiting_execution",
        decision="propose",
        lifecycle="submitted",
        message=(
            preferred_output.message
            if preferred_output is not None and preferred_describes_selection
            else "Current compiled physical-agent obligations."
        ),
        proposal_id=(next(iter(proposal_ids)) if len(proposal_ids) == 1 else None),
    )
    return materialize_agent_output(
        compiled,
        actions=actions,
        feedback=feedback,
        claim_owners=claim_owners,
    )


def project_chat_plan(
    plan_document: dict[str, Any],
    *,
    actions: dict[str, Any],
    feedback: dict[str, Any],
    claim_owners: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    plan_value = plan_document.get("plan") or {}
    plan = (
        plan_value
        if isinstance(plan_value, ChatPlan)
        else ChatPlan.model_validate(plan_value)
    )
    projected = current_agent_output(
        actions=actions,
        feedback=feedback,
        claim_owners=claim_owners,
        preferred=plan.agent_output,
    )
    if projected is None:
        return {**plan_document, "plan": plan}
    return {
        **plan_document,
        "plan": plan.model_copy(
            update={
                "agent_output": projected.model_dump(mode="json", by_alias=True)
            }
        ),
    }


def _output_status(output: AgentOutput, tasks: list[AgentTask]) -> AgentOutputStatus:
    if output.status in {"refused", "unavailable", "draft"}:
        return output.status
    statuses = {task.status for task in tasks}
    if statuses & {"rejected", "failed"}:
        return "failed"
    if any(
        task.status == "skipped"
        and task.kind in {"safety_gate", "physical_action"}
        for task in tasks
    ):
        # A skipped mandatory precondition/execution task is terminal. This is
        # especially important for an action rejected through the board when
        # no ApprovalTask was required (and therefore no task is "rejected").
        return "failed"
    approvals = [task for task in tasks if task.kind == "approval"]
    if any(task.status in {"requested", "waiting"} for task in approvals):
        return "waiting_approval"
    if statuses & {"checking"}:
        return "executing"
    physical = [task for task in tasks if task.kind == "physical_action"]
    verification = [task for task in tasks if task.kind == "verification"]
    if any(task.status == "skipped" for task in verification):
        return "failed"
    if physical and all(task.status == "completed" for task in physical):
        if all(task.status in {"passed", "completed"} for task in verification):
            return "completed"
    return "waiting_execution"


def _physical_status_for_action(
    action_state: str | None,
    *,
    gate_event: dict[str, Any] | None,
    approval_status: str,
) -> str:
    if approval_status == "rejected" or str((gate_event or {}).get("status")) == "rejected":
        return "skipped"
    if action_state == "completed":
        return "completed"
    if action_state == "cancelled":
        return "failed"
    if action_state == "in_progress":
        return "checking"
    return "waiting"


def _action_states(actions: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for status in ("pending", "in_progress", "completed", "cancelled"):
        for action in _actions_for_status(actions, status):
            result[action.id] = status
    return result


def _action_values(actions: dict[str, Any]) -> dict[str, Action]:
    result: dict[str, Action] = {}
    for status in ("pending", "in_progress", "completed", "cancelled"):
        for action in _actions_for_status(actions, status):
            result[action.id] = action
    return result


def _active_actions(actions: dict[str, Any]) -> list[Action]:
    return [
        *_actions_for_status(actions, "pending"),
        *_actions_for_status(actions, "in_progress"),
    ]


def _actions_for_status(actions: dict[str, Any], status: str) -> list[Action]:
    values = actions.get(status) or []
    return [
        value if isinstance(value, Action) else Action.model_validate(value)
        for value in values
    ]


def _feedback_events(feedback: dict[str, Any]) -> list[dict[str, Any]]:
    history = feedback.get("history")
    if isinstance(history, list) and history:
        return [item for item in history if isinstance(item, dict)]
    latest = feedback.get("latest")
    return [latest] if isinstance(latest, dict) and latest else []


def _latest_events(
    events: list[dict[str, Any]],
    event_name: str,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("event") != event_name or not event.get("action_id"):
            continue
        result[str(event["action_id"])] = event
    return result


def _latest_gate_event_for_owner(
    events: list[dict[str, Any]],
    *,
    action_id: str,
    executor_id: str,
) -> dict[str, Any] | None:
    for event in reversed(events):
        if (
            event.get("event") == "safety_gate"
            and str(event.get("action_id") or "") == action_id
            and str(event.get("executor_id") or "") == executor_id
        ):
            return event
    return None


def _preclaim_dependency_rejection_owner(
    events: list[dict[str, Any]],
    *,
    action_id: str,
    gate_event: dict[str, Any] | None,
) -> str | None:
    if (
        not _is_authoritative_gate_event(gate_event, action_id)
        or gate_event.get("status") != "rejected"
        or gate_event.get("decision") != "deny"
        or gate_event.get("code") != "safety.dependencies.completed"
    ):
        return None
    executor_id = str(gate_event.get("executor_id") or "")
    if not executor_id:
        return None
    for event in reversed(events):
        if (
            event.get("event") in {None, "action_result"}
            and str(event.get("action_id") or "") == action_id
            and str(event.get("executor_id") or "") == executor_id
            and str(event.get("status") or "") in {"failed", "cancelled"}
        ):
            # This fallback is intentionally denial-only. It exists for the
            # watch-owned dependency cascade, which terminalizes a pending
            # action before it is claimable. Feedback can never establish an
            # allow/pass owner for completed execution.
            return executor_id
    return None


def _is_authoritative_gate_event(
    event: dict[str, Any] | None,
    action_id: str,
) -> bool:
    if event is None:
        return False
    status = str(event.get("status") or "")
    decision = str(event.get("decision") or "")
    return bool(
        event.get("task_id") == safety_gate_task_id(action_id)
        and event.get("actor") == "watch"
        and event.get("owner") == "watch"
        and event.get("mandatory") is True
        and event.get("policy_source") == "SAFETY.md"
        and (status, decision) in {("passed", "allow"), ("rejected", "deny")}
    )


def _approval_status(action: Action | None) -> str:
    if action is None or not isinstance(action.metadata, dict):
        return ""
    approval = action.metadata.get("approval")
    if not isinstance(approval, dict):
        return ""
    return str(approval.get("status") or "")


def _proposal_id(action: Action) -> str | None:
    metadata = action.metadata if isinstance(action.metadata, dict) else {}
    correlation = metadata.get("correlation")
    if not isinstance(correlation, dict) or not correlation.get("proposal_id"):
        return None
    return str(correlation["proposal_id"])


def _coerce_output(
    output: AgentOutput | dict[str, Any] | None,
) -> AgentOutput | None:
    if output is None:
        return None
    return output if isinstance(output, AgentOutput) else AgentOutput.model_validate(output)
