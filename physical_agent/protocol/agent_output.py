from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict, Field, model_validator

from physical_agent.protocol.actions import parse_action_metadata
from physical_agent.protocol.schemas import Action, StrictModel


AGENT_OUTPUT_SCHEMA = "physical-agent/agent-output/v1"
AgentOutputStatus = Literal[
    "draft",
    "waiting_approval",
    "waiting_execution",
    "executing",
    "completed",
    "failed",
    "refused",
    "unavailable",
]
AgentDecision = Literal["propose", "reply", "ask", "wait", "refuse", "stop"]
AgentTaskKind = Literal[
    "approval",
    "safety_gate",
    "physical_action",
    "verification",
]
AgentTaskOwner = Literal["human", "watch"]
AgentTaskStatus = Literal[
    "not_scheduled",
    "requested",
    "waiting",
    "queued",
    "checking",
    "passed",
    "rejected",
    "completed",
    "failed",
    "skipped",
]
SafetyCheckStatus = Literal["passed", "rejected", "error", "skipped"]


class SafetyCheckSpec(StrictModel):
    """One execution-time check owned by the trusted SafetyGate."""

    code: str
    description: str


class SafetyCheckResult(StrictModel):
    """Structured evidence emitted by watch when SafetyGate evaluates an action."""

    code: str
    status: SafetyCheckStatus
    message: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class AgentTask(StrictModel):
    """A system-compiled task in the public Agent output graph.

    These tasks are not driver Actions and are never accepted from an LLM or
    API caller. ``origin`` and the graph invariants make the trust boundary
    explicit while the existing Action board remains wire-compatible.
    """

    id: str
    kind: AgentTaskKind
    owner: AgentTaskOwner
    status: AgentTaskStatus
    label: str
    action_id: str
    depends_on: list[str] = Field(default_factory=list)
    origin: Literal["plan_compiler"] = "plan_compiler"
    mandatory: bool = False
    policy_source: str | None = None
    checks: list[SafetyCheckSpec] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class AgentOutput(StrictModel):
    """Trusted, compiled output exposed by Physical Agent surfaces.

    It is deliberately distinct from a raw model response. The model proposes
    Action intents; the application compiler injects mandatory safety work.
    """

    model_config = ConfigDict(populate_by_name=True)

    schema_: str = Field(default=AGENT_OUTPUT_SCHEMA, alias="schema")
    status: AgentOutputStatus
    decision: AgentDecision
    lifecycle: Literal["draft", "submitted"]
    message: str
    proposal_id: str | None = None
    tasks: list[AgentTask] = Field(default_factory=list)
    actions: list[Action] = Field(default_factory=list)
    refusal_reason: str | None = None

    @property
    def schema(self) -> str:
        return self.schema_

    @model_validator(mode="after")
    def validate_task_graph(self) -> "AgentOutput":
        action_ids = [action.id for action in self.actions]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("AgentOutput action ids must be unique.")

        action_by_id = {action.id: action for action in self.actions}
        task_by_id = {task.id: task for task in self.tasks}
        if len(task_by_id) != len(self.tasks):
            raise ValueError("AgentOutput task ids must be unique.")
        for task in self.tasks:
            if task.action_id not in action_ids:
                raise ValueError(f"Task {task.id} targets an unknown action.")
            unknown_dependencies = set(task.depends_on) - set(task_by_id)
            allowed_external_dependencies: set[str] = set()
            if task.kind == "safety_gate":
                action = action_by_id[task.action_id]
                allowed_external_dependencies = {
                    physical_action_task_id(dependency)
                    for dependency in action.depends_on
                    if dependency not in action_by_id
                }
            invalid_dependencies = (
                unknown_dependencies - allowed_external_dependencies
            )
            if invalid_dependencies:
                raise ValueError(
                    f"Task {task.id} has unknown dependencies: "
                    + ", ".join(sorted(invalid_dependencies))
                )

        for action in self.actions:
            validation_metadata = dict(action.metadata or {})
            validation_metadata.pop("safety_intent", None)
            metadata = parse_action_metadata(validation_metadata)
            approvals = [
                task
                for task in self.tasks
                if task.kind == "approval" and task.action_id == action.id
            ]
            gates = [
                task
                for task in self.tasks
                if task.kind == "safety_gate" and task.action_id == action.id
            ]
            physical = [
                task
                for task in self.tasks
                if task.kind == "physical_action" and task.action_id == action.id
            ]
            if len(gates) != 1 or len(physical) != 1:
                raise ValueError(
                    f"Action {action.id} requires exactly one safety_gate task "
                    "and one physical_action task."
                )
            gate = gates[0]
            action_task = physical[0]
            if gate.id != safety_gate_task_id(action.id):
                raise ValueError(f"Safety task for {action.id} has a non-canonical id.")
            if not gate.mandatory or gate.owner != "watch":
                raise ValueError(f"Safety task for {action.id} must be mandatory and watch-owned.")
            if gate.policy_source != "SAFETY.md":
                raise ValueError(
                    f"Safety task for {action.id} must declare SAFETY.md as its policy source."
                )
            expected_checks = [spec.code for spec in safety_check_specs()]
            if [check.code for check in gate.checks] != expected_checks:
                raise ValueError(
                    f"Safety task for {action.id} must declare the canonical checks."
                )
            required_action_dependencies = {
                physical_action_task_id(dependency)
                for dependency in action.depends_on
            }
            if not required_action_dependencies.issubset(gate.depends_on):
                raise ValueError(
                    f"Safety task for {action.id} is missing physical action dependencies."
                )
            if len(approvals) > 1:
                raise ValueError(f"Action {action.id} has more than one approval task.")
            if (
                self.lifecycle == "submitted"
                and metadata.approval is not None
                and metadata.approval.required
                and len(approvals) != 1
            ):
                # Submitted Action metadata has crossed the authoritative
                # proposal/state boundary. A required approval must therefore
                # be represented in the trusted task graph; draft metadata is
                # still advisory and may be overridden by capability facts.
                raise ValueError(
                    f"Action {action.id} requires exactly one approval task."
                )
            if approvals:
                approval = approvals[0]
                if approval.id != approval_task_id(action.id):
                    raise ValueError(
                        f"Approval task for {action.id} has a non-canonical id."
                    )
                if not approval.mandatory or approval.owner != "human":
                    raise ValueError(
                        f"Approval task for {action.id} must be mandatory and human-owned."
                    )
                if approval.id not in gate.depends_on:
                    raise ValueError(
                        f"Safety task for {action.id} must depend on its approval task."
                    )
            if action_task.id != physical_action_task_id(action.id):
                raise ValueError(
                    f"Physical action task for {action.id} has a non-canonical id."
                )
            if not action_task.mandatory or action_task.owner != "watch":
                raise ValueError(
                    f"Physical action task for {action.id} must be mandatory and watch-owned."
                )
            if gate.id not in action_task.depends_on:
                raise ValueError(f"Physical action task for {action.id} must depend on its SafetyGate task.")

            verifications = [
                task
                for task in self.tasks
                if task.kind == "verification" and task.action_id == action.id
            ]
            if len(verifications) > 1:
                raise ValueError(f"Action {action.id} has more than one verification task.")
            if metadata.expected and len(verifications) != 1:
                raise ValueError(f"Action {action.id} requires one verification task.")
            if not metadata.expected and verifications:
                raise ValueError(
                    f"Action {action.id} cannot have verification without expected checks."
                )
            if verifications:
                verification = verifications[0]
                if verification.id != verification_task_id(action.id):
                    raise ValueError(
                        f"Verification task for {action.id} has a non-canonical id."
                    )
                if verification.owner != "watch":
                    raise ValueError(
                        f"Verification task for {action.id} must be watch-owned."
                    )
                if action_task.id not in verification.depends_on:
                    raise ValueError(
                        f"Verification task for {action.id} must depend on its physical action."
                    )

        _assert_acyclic(task_by_id)
        return self


def approval_task_id(action_id: str) -> str:
    return f"task:approval:{action_id}"


def safety_gate_task_id(action_id: str) -> str:
    return f"task:safety_gate:{action_id}"


def physical_action_task_id(action_id: str) -> str:
    return f"task:physical_action:{action_id}"


def verification_task_id(action_id: str) -> str:
    return f"task:verification:{action_id}"


def safety_check_specs() -> list[SafetyCheckSpec]:
    return [
        SafetyCheckSpec(code="safety.action_id.unique", description="Reject duplicate action ids."),
        SafetyCheckSpec(code="safety.dependencies.completed", description="Require completed action dependencies."),
        SafetyCheckSpec(code="safety.robot.known", description="Require a live, published robot."),
        SafetyCheckSpec(code="safety.robot.ready", description="Require watch connection and heartbeat state to permit new work."),
        SafetyCheckSpec(code="safety.capability.known", description="Require a published driver capability."),
        SafetyCheckSpec(code="safety.autonomy.allowed", description="Apply the SAFETY.md autonomy policy."),
        SafetyCheckSpec(code="safety.approval.satisfied", description="Require backend-authoritative approval when configured."),
        SafetyCheckSpec(code="safety.params.schema", description="Validate parameters against the capability schema."),
        SafetyCheckSpec(code="safety.constraints.satisfied", description="Enforce capability constraints such as bounds."),
        SafetyCheckSpec(code="safety.timeout.allowed", description="Enforce the maximum action timeout policy."),
    ]


def _assert_acyclic(tasks: dict[str, AgentTask]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visited:
            return
        if task_id in visiting:
            raise ValueError("AgentOutput task graph must be acyclic.")
        visiting.add(task_id)
        for dependency in tasks[task_id].depends_on:
            if dependency in tasks:
                visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in tasks:
        visit(task_id)
