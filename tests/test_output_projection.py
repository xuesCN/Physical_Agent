from __future__ import annotations

from physical_agent.application.output_projection import (
    current_agent_output,
    materialize_agent_output,
    project_chat_plan,
)
from physical_agent.application.plan_compiler import compile_agent_output
from physical_agent.protocol.schemas import Action, ChatPlan


def _gate_event(*, status: str, decision: str) -> dict[str, object]:
    return {
        "event": "safety_gate",
        "task_id": "task:safety_gate:act_001",
        "action_id": "act_001",
        "status": status,
        "decision": decision,
        "actor": "watch",
        "owner": "watch",
        "mandatory": True,
        "policy_source": "SAFETY.md",
    }


def _compiled(*, expected: bool = False):
    metadata = (
        {
            "expected": [
                {"path": "robots.arm_1.status", "op": "eq", "value": "idle"}
            ]
        }
        if expected
        else {}
    )
    return compile_agent_output(
        [
            Action(
                id="act_001",
                robot="arm_1",
                capability="observe",
                metadata=metadata,
            )
        ],
        status="waiting_execution",
        decision="propose",
        lifecycle="submitted",
        message="Observe.",
        proposal_id="proposal_test",
    )


def test_projection_materializes_gate_and_running_physical_task():
    action = _compiled().actions[0]
    output = materialize_agent_output(
        _compiled(),
        actions={
            "pending": [],
            "in_progress": [action],
            "completed": [],
            "cancelled": [],
        },
        feedback={
            "history": [
                _gate_event(status="passed", decision="allow")
            ]
        },
    )
    tasks = {task.kind: task for task in output.tasks}

    assert output.status == "executing"
    assert tasks["safety_gate"].status == "passed"
    assert tasks["physical_action"].status == "checking"
    assert tasks["safety_gate"].details["last_decision"]["decision"] == "allow"


def test_projection_waits_for_and_materializes_verification():
    action = _compiled(expected=True).actions[0]
    actions = {
        "pending": [],
        "in_progress": [],
        "completed": [action],
        "cancelled": [],
    }
    gate = _gate_event(status="passed", decision="allow")
    checking = materialize_agent_output(
        _compiled(expected=True),
        actions=actions,
        feedback={"history": [gate]},
    )
    completed = materialize_agent_output(
        _compiled(expected=True),
        actions=actions,
        feedback={
            "history": [
                gate,
                {
                    "event": "expectation_check",
                    "action_id": "act_001",
                    "status": "verified",
                    "message": "verified",
                },
            ]
        },
    )

    assert checking.status == "executing"
    assert next(task for task in checking.tasks if task.kind == "verification").status == "checking"
    assert completed.status == "completed"
    assert next(task for task in completed.tasks if task.kind == "verification").status == "passed"


def test_completed_action_without_gate_evidence_fails_closed():
    action = _compiled().actions[0]
    output = materialize_agent_output(
        _compiled(),
        actions={
            "pending": [],
            "in_progress": [],
            "completed": [action],
            "cancelled": [],
        },
        feedback={"history": []},
    )
    tasks = {task.kind: task for task in output.tasks}

    assert output.status == "failed"
    assert tasks["safety_gate"].status == "failed"
    assert tasks["safety_gate"].details["projection_error"]["code"] == (
        "safety.gate.evidence_missing"
    )
    # The projection does not rewrite the board's physical completion fact.
    assert tasks["physical_action"].status == "completed"


def test_forged_gate_feedback_cannot_satisfy_mandatory_gate():
    action = _compiled().actions[0]
    forged = _gate_event(status="passed", decision="allow")
    forged["actor"] = "agent"
    output = materialize_agent_output(
        _compiled(),
        actions={
            "pending": [],
            "in_progress": [],
            "completed": [action],
            "cancelled": [],
        },
        feedback={"history": [forged]},
    )
    tasks = {task.kind: task for task in output.tasks}

    assert output.status == "failed"
    assert tasks["safety_gate"].status == "failed"
    assert tasks["safety_gate"].details["projection_error"]["code"] == (
        "safety.gate.evidence_invalid"
    )


def test_recovered_pending_action_does_not_reuse_old_passed_gate():
    action = _compiled().actions[0]
    output = materialize_agent_output(
        _compiled(),
        actions={
            "pending": [action],
            "in_progress": [],
            "completed": [],
            "cancelled": [],
        },
        feedback={"history": [_gate_event(status="passed", decision="allow")]},
    )
    tasks = {task.kind: task for task in output.tasks}

    assert output.status == "waiting_execution"
    assert tasks["safety_gate"].status == "queued"
    assert tasks["physical_action"].status == "waiting"


def test_pending_action_with_forged_gate_feedback_still_fails_closed():
    action = _compiled().actions[0]
    forged = _gate_event(status="passed", decision="allow")
    forged["actor"] = "agent"
    output = materialize_agent_output(
        _compiled(),
        actions={
            "pending": [action],
            "in_progress": [],
            "completed": [],
            "cancelled": [],
        },
        feedback={"history": [forged]},
    )
    gate = next(task for task in output.tasks if task.kind == "safety_gate")

    assert output.status == "failed"
    assert gate.status == "failed"
    assert gate.details["projection_error"]["code"] == (
        "safety.gate.evidence_invalid"
    )


def test_rejected_action_without_approval_or_verification_is_terminal_failed():
    action = Action(
        id="act_optional_approval",
        robot="arm_1",
        capability="observe",
        metadata={"approval": {"required": False, "status": "rejected"}},
    )
    compiled = compile_agent_output(
        [action],
        status="waiting_execution",
        decision="propose",
        lifecycle="submitted",
        message="Observe.",
    )
    output = materialize_agent_output(
        compiled,
        actions={
            "pending": [],
            "in_progress": [],
            "completed": [],
            "cancelled": [action],
        },
        feedback={"history": []},
    )
    tasks = {task.kind: task for task in output.tasks}

    assert output.status == "failed"
    assert set(tasks) == {"safety_gate", "physical_action"}
    assert tasks["safety_gate"].status == "skipped"
    assert tasks["physical_action"].status == "skipped"


def test_rejected_action_without_required_approval_is_terminal_failed():
    action = Action(
        id="act_optional_approval",
        robot="arm_1",
        capability="observe",
        metadata={
            "approval": {"required": False, "status": "rejected"},
            "expected": [
                {"path": "robots.arm_1.status", "op": "eq", "value": "idle"}
            ],
        },
    )
    compiled = compile_agent_output(
        [action],
        status="waiting_execution",
        decision="propose",
        lifecycle="submitted",
        message="Observe.",
    )
    output = materialize_agent_output(
        compiled,
        actions={
            "pending": [],
            "in_progress": [],
            "completed": [],
            "cancelled": [action],
        },
        feedback={"history": []},
    )
    tasks = {task.kind: task for task in output.tasks}

    assert output.status == "failed"
    assert "approval" not in tasks
    assert tasks["safety_gate"].status == "skipped"
    assert tasks["physical_action"].status == "skipped"
    assert tasks["verification"].status == "skipped"


def test_gate_rejection_skips_execution_and_verification_tasks():
    action = _compiled(expected=True).actions[0]
    output = materialize_agent_output(
        _compiled(expected=True),
        actions={
            "pending": [],
            "in_progress": [],
            "completed": [],
            "cancelled": [action],
        },
        feedback={
            "history": [
                _gate_event(status="rejected", decision="deny")
            ]
        },
    )
    tasks = {task.kind: task for task in output.tasks}

    assert output.status == "failed"
    assert tasks["safety_gate"].status == "rejected"
    assert tasks["physical_action"].status == "skipped"
    assert tasks["verification"].status == "skipped"


def test_current_projection_rebuilds_active_tasks_after_chat_overwrites_plan():
    action = Action(
        id="act_active",
        robot="arm_1",
        capability="observe",
        metadata={
            "correlation": {
                "session_id": "workspace",
                "proposal_id": "proposal_active",
            }
        },
    )
    actions = {
        "pending": [action],
        "in_progress": [],
        "completed": [],
        "cancelled": [],
    }
    projected = project_chat_plan(
        {
            "metadata": {"revision": 2},
            "plan": ChatPlan(status="answered", intent="chat", summary="hello"),
        },
        actions=actions,
        feedback={"history": []},
    )

    output = projected["plan"].agent_output
    assert output is not None
    assert output["proposal_id"] == "proposal_active"
    assert {task["kind"] for task in output["tasks"]} == {
        "safety_gate",
        "physical_action",
    }
    assert current_agent_output(
        actions=actions,
        feedback={"history": []},
        preferred=None,
    ) is not None


def test_chat_plan_ignores_retired_top_level_actions_and_projects_only_agent_output():
    stale_action = Action(
        id="act_stale",
        robot="arm_1",
        capability="observe",
    )
    active_action = Action(
        id="act_active",
        robot="arm_1",
        capability="observe",
        metadata={
            "correlation": {
                "session_id": "workspace",
                "proposal_id": "proposal_active",
            }
        },
    )
    legacy_plan = ChatPlan.model_validate(
        {
            "status": "proposed_actions",
            "intent": "act",
            "summary": "legacy persisted plan",
            "actions": [stale_action.model_dump(mode="json")],
        }
    )

    projected = project_chat_plan(
        {"metadata": {"revision": 3}, "plan": legacy_plan},
        actions={
            "pending": [active_action],
            "in_progress": [],
            "completed": [],
            "cancelled": [],
        },
        feedback={"history": []},
    )
    serialized = projected["plan"].model_dump(mode="json")

    assert "actions" not in serialized
    assert [
        action["id"] for action in serialized["agent_output"]["actions"]
    ] == ["act_active"]
