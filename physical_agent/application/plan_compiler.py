from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from physical_agent.protocol.actions import parse_action_metadata
from physical_agent.protocol.agent_output import (
    AgentOutput,
    AgentOutputStatus,
    AgentTask,
    AgentTaskStatus,
    approval_task_id,
    physical_action_task_id,
    safety_check_specs,
    safety_gate_task_id,
    verification_task_id,
)
from physical_agent.protocol.schemas import Action


OutputLifecycle = Literal["draft", "submitted"]


class PlanCompiler:
    """Compile untrusted action intents into the public, trusted task graph.

    The compiler is an application boundary, not an LLM helper. Callers can
    suggest ``Action`` and advisory ``SafetyIntent`` values, but they cannot
    create, remove, satisfy, or reorder the mandatory watch-owned gate task.
    """

    def compile(
        self,
        actions: Iterable[Action],
        *,
        status: AgentOutputStatus,
        decision: Literal["propose", "reply", "ask", "wait", "refuse", "stop"],
        lifecycle: OutputLifecycle,
        message: str,
        proposal_id: str | None = None,
        refusal_reason: str | None = None,
        capabilities: dict[str, object] | None = None,
        safety_rules: dict[str, object] | None = None,
    ) -> AgentOutput:
        compiled_actions = list(actions)
        action_ids = {action.id for action in compiled_actions}
        tasks: list[AgentTask] = []

        for action in compiled_actions:
            metadata, invalid_safety_intent_ignored = _metadata_for_compilation(
                action
            )
            approval = metadata.approval
            fact_requirement = _approval_required_from_facts(
                action,
                capabilities=capabilities,
                safety_rules=safety_rules,
            )
            approval_required = (
                fact_requirement
                if fact_requirement is not None
                else bool(approval and approval.required)
            )
            approval_status = approval.status if approval is not None else "not_required"
            approval_id = approval_task_id(action.id)
            gate_id = safety_gate_task_id(action.id)
            action_task_id = physical_action_task_id(action.id)

            if approval_required:
                tasks.append(
                    AgentTask(
                        id=approval_id,
                        kind="approval",
                        owner="human",
                        status=_approval_task_status(lifecycle, approval_status),
                        label=f"Approve {action.id}",
                        action_id=action.id,
                        mandatory=True,
                        details={
                            "approval_status": approval_status,
                            "reason": approval.reason if approval is not None else None,
                        },
                    )
                )

            external_action_ids = [
                dependency
                for dependency in action.depends_on
                if dependency not in action_ids
            ]
            gate_dependencies = [
                physical_action_task_id(dependency)
                for dependency in action.depends_on
            ]
            if approval_required:
                gate_dependencies.insert(0, approval_id)

            safety_intent = (
                metadata.safety_intent.model_dump(mode="json")
                if metadata.safety_intent is not None
                else None
            )
            gate_details: dict[str, object] = {
                "action_dependencies": list(action.depends_on),
                "external_action_dependencies": external_action_ids,
                "advisory_only": True,
            }
            if invalid_safety_intent_ignored:
                gate_details["invalid_safety_intent_ignored"] = True
            if safety_intent is not None:
                gate_details["safety_intent"] = safety_intent

            gate_status = _gate_task_status(
                lifecycle,
                approval_status=approval_status,
                has_dependencies=bool(action.depends_on),
            )
            tasks.append(
                AgentTask(
                    id=gate_id,
                    kind="safety_gate",
                    owner="watch",
                    status=gate_status,
                    label=f"Safety gate for {action.id}",
                    action_id=action.id,
                    depends_on=gate_dependencies,
                    mandatory=True,
                    policy_source="SAFETY.md",
                    checks=safety_check_specs(),
                    details=gate_details,
                )
            )

            physical_status: AgentTaskStatus
            if lifecycle == "draft":
                physical_status = "not_scheduled"
            elif approval_status == "rejected":
                physical_status = "skipped"
            else:
                physical_status = "waiting"
            tasks.append(
                AgentTask(
                    id=action_task_id,
                    kind="physical_action",
                    owner="watch",
                    status=physical_status,
                    label=f"Execute {action.id}: {action.capability}",
                    action_id=action.id,
                    depends_on=[gate_id],
                    mandatory=True,
                    details={
                        "robot": action.robot,
                        "capability": action.capability,
                    },
                )
            )

            if metadata.expected:
                tasks.append(
                    AgentTask(
                        id=verification_task_id(action.id),
                        kind="verification",
                        owner="watch",
                        status=(
                            "not_scheduled"
                            if lifecycle == "draft"
                            else "waiting"
                        ),
                        label=f"Verify outcome of {action.id}",
                        action_id=action.id,
                        depends_on=[action_task_id],
                        mandatory=False,
                        details={
                            "expected": metadata.expected,
                            "role": "post_execution_diagnostic",
                        },
                    )
                )

        return AgentOutput(
            status=status,
            decision=decision,
            lifecycle=lifecycle,
            message=message,
            proposal_id=proposal_id,
            tasks=tasks,
            actions=compiled_actions,
            refusal_reason=refusal_reason,
        )


def compile_agent_output(
    actions: Iterable[Action],
    *,
    status: AgentOutputStatus,
    decision: Literal["propose", "reply", "ask", "wait", "refuse", "stop"],
    lifecycle: OutputLifecycle,
    message: str,
    proposal_id: str | None = None,
    refusal_reason: str | None = None,
    capabilities: dict[str, object] | None = None,
    safety_rules: dict[str, object] | None = None,
) -> AgentOutput:
    """Functional facade used by protocol adapters and tests."""

    return PlanCompiler().compile(
        actions,
        status=status,
        decision=decision,
        lifecycle=lifecycle,
        message=message,
        proposal_id=proposal_id,
        refusal_reason=refusal_reason,
        capabilities=capabilities,
        safety_rules=safety_rules,
    )


def task_graph_steps(output: AgentOutput) -> list[str]:
    """Render the trusted graph into the legacy human-readable plan steps."""

    return [
        f"{task.kind}: {task.label} [{task.status}; owner={task.owner}]"
        for task in output.tasks
    ]


def _approval_task_status(
    lifecycle: OutputLifecycle,
    approval_status: str,
) -> AgentTaskStatus:
    if lifecycle == "draft":
        return "not_scheduled"
    if approval_status == "approved":
        return "completed"
    if approval_status == "rejected":
        return "rejected"
    return "requested"


def _gate_task_status(
    lifecycle: OutputLifecycle,
    *,
    approval_status: str,
    has_dependencies: bool,
) -> AgentTaskStatus:
    if lifecycle == "draft":
        return "not_scheduled"
    if approval_status == "rejected":
        return "skipped"
    if approval_status == "pending" or has_dependencies:
        return "waiting"
    return "queued"


def _approval_required_from_facts(
    action: Action,
    *,
    capabilities: dict[str, object] | None,
    safety_rules: dict[str, object] | None,
) -> bool | None:
    """Resolve approval from trusted published facts when they are available."""

    if not isinstance(capabilities, dict):
        return None
    robots_value = capabilities.get("robots")
    if not isinstance(robots_value, dict):
        return None
    robot_value = robots_value.get(action.robot)
    if not isinstance(robot_value, dict):
        return None
    rules = safety_rules if isinstance(safety_rules, dict) else {}
    if robot_value.get("requires_approval") and rules.get(
        "require_human_approval_for_real_hardware",
        True,
    ):
        return True
    capability_values = robot_value.get("capabilities")
    if not isinstance(capability_values, list):
        return False
    for capability in capability_values:
        if not isinstance(capability, dict):
            continue
        if capability.get("name") == action.capability:
            return bool(capability.get("requires_approval"))
    return False


def _metadata_for_compilation(action: Action):
    try:
        return parse_action_metadata(action.metadata), False
    except ValueError:
        # SafetyIntent is advisory. Malformed advisory reasoning must not hide
        # or block the mandatory system Gate for an action already in state.
        cleaned = dict(action.metadata or {})
        if "safety_intent" not in cleaned:
            raise
        cleaned.pop("safety_intent", None)
        return parse_action_metadata(cleaned), True
