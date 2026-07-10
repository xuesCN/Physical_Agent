import pytest

from physical_agent.protocol.agent_output import safety_check_specs
from physical_agent.protocol.schemas import Action, Capability, RobotRuntimeProfile
from physical_agent.watch.safety import SafetyGate


def _gate(**kwargs):
    capabilities = [
        Capability(
            name="move_to",
            description="move",
            params_schema={
                "type": "object",
                "required": ["x"],
                "properties": {"x": {"type": "number"}},
                "additionalProperties": False,
            },
            constraints={"bounds": {"x": [-1.0, 1.0]}},
        )
    ]
    robots = {
        "arm_1": RobotRuntimeProfile(
            robot_id="arm_1",
            kind="arm",
            driver="mock_arm",
            status="connected",
            capabilities=capabilities,
        )
    }
    return SafetyGate(robots=robots, safety_rules={}, **kwargs)


def _approval_gate():
    capabilities = [
        Capability(
            name="move_to",
            description="move",
            params_schema={
                "type": "object",
                "required": ["x"],
                "properties": {"x": {"type": "number"}},
                "additionalProperties": False,
            },
            constraints={"bounds": {"x": [-1.0, 1.0]}},
            requires_approval=True,
        )
    ]
    robots = {
        "arm_1": RobotRuntimeProfile(
            robot_id="arm_1",
            kind="arm",
            driver="mock_arm",
            status="connected",
            capabilities=capabilities,
        )
    }
    return SafetyGate(robots=robots, safety_rules={})


def _gate_with_bounds(bounds):
    capability = Capability(
        name="move",
        description="move",
        params_schema={"type": "object"},
        constraints={"bounds": bounds},
    )
    return SafetyGate(
        robots={
            "arm_1": RobotRuntimeProfile(
                robot_id="arm_1",
                kind="arm",
                driver="mock",
                status="connected",
                capabilities=[capability],
            )
        }
    )


def test_unknown_robot_rejected():
    decision = _gate().validate(Action(id="a", robot="missing", capability="move_to", params={"x": 0}))
    assert not decision.ok
    assert "Unknown robot" in decision.message


def test_unknown_capability_rejected():
    decision = _gate().validate(Action(id="a", robot="arm_1", capability="fly", params={}))
    assert not decision.ok
    assert "does not expose" in decision.message


def test_invalid_params_rejected():
    decision = _gate().validate(Action(id="a", robot="arm_1", capability="move_to", params={}))
    assert not decision.ok
    assert "Invalid params" in decision.message


def test_out_of_bounds_rejected():
    decision = _gate().validate(Action(id="a", robot="arm_1", capability="move_to", params={"x": 2.0}))
    assert not decision.ok
    assert "outside allowed bounds" in decision.message


def test_duplicate_action_id_rejected():
    decision = _gate(executed_action_ids={"a"}).validate(
        Action(id="a", robot="arm_1", capability="move_to", params={"x": 0})
    )
    assert not decision.ok
    assert "Duplicate" in decision.message


def test_unmet_depends_on_rejected():
    decision = _gate(completed_action_ids=set()).validate(
        Action(id="a", robot="arm_1", capability="move_to", params={"x": 0}, depends_on=["b"])
    )
    assert not decision.ok
    assert "unmet dependency" in decision.message


def test_requires_approval_rejected_until_action_metadata_is_approved():
    gate = _approval_gate()

    missing = gate.validate(
        Action(id="a", robot="arm_1", capability="move_to", params={"x": 0})
    )
    approved = gate.validate(
        Action(
            id="b",
            robot="arm_1",
            capability="move_to",
            params={"x": 0},
            metadata={"approval": {"required": False, "status": "approved"}},
        )
    )

    assert not missing.ok
    assert "requires approved human approval" in missing.message
    assert approved.ok


def test_approval_does_not_bypass_schema_or_bounds():
    gate = _approval_gate()

    decision = gate.validate(
        Action(
            id="a",
            robot="arm_1",
            capability="move_to",
            params={"x": 2.0},
            metadata={"approval": {"required": True, "status": "approved"}},
        )
    )

    assert not decision.ok
    assert "outside allowed bounds" in decision.message


def test_safety_decision_exposes_stable_structured_checks():
    accepted = _gate().validate(
        Action(id="accepted", robot="arm_1", capability="move_to", params={"x": 0})
    )
    rejected = _gate().validate(
        Action(id="rejected", robot="arm_1", capability="move_to", params={"x": 2})
    )
    expected_codes = [spec.code for spec in safety_check_specs()]

    assert accepted.ok is True
    assert accepted.outcome == "allow"
    assert accepted.code == "safety.accepted"
    assert [check.code for check in accepted.checks] == expected_codes
    assert {check.status for check in accepted.checks} == {"passed"}

    assert rejected.ok is False
    assert rejected.outcome == "deny"
    assert rejected.code == "safety.constraints.satisfied"
    assert [check.code for check in rejected.checks] == expected_codes
    statuses = {check.code: check.status for check in rejected.checks}
    assert statuses["safety.constraints.satisfied"] == "rejected"
    assert statuses["safety.timeout.allowed"] == "skipped"


def test_malformed_constraint_values_fail_closed_instead_of_crashing():
    decision = _gate_with_bounds({"x": [-1.0, 1.0]}).validate(
        Action(id="a", robot="arm_1", capability="move", params={"x": "left"})
    )

    assert decision.ok is False
    assert decision.code == "safety.constraints.satisfied"
    rejected = next(check for check in decision.checks if check.status == "rejected")
    assert rejected.evidence["error_type"] == "ConstraintTypeError"
    assert rejected.evidence["reason"] == "parameter_not_numeric"


@pytest.mark.parametrize(
    ("bounds", "expected_reason"),
    [
        (None, "bounds_not_object"),
        ([-1.0, 1.0], "bounds_not_object"),
        ({"x": [-1.0]}, "axis_bounds_invalid_shape"),
        ({"x": [-1.0, 1.0, 2.0]}, "axis_bounds_invalid_shape"),
        ({"x": "[-1, 1]"}, "axis_bounds_invalid_shape"),
        ({"x": ["low", 1.0]}, "bound_not_numeric"),
        ({"x": [-1.0, True]}, "bound_not_numeric"),
        ({"x": [float("nan"), 1.0]}, "bound_not_finite"),
        ({"x": [-1.0, float("inf")]}, "bound_not_finite"),
        ({"x": [2.0, 1.0]}, "bounds_inverted"),
    ],
)
def test_malformed_bounds_configuration_is_structurally_rejected(
    bounds, expected_reason
):
    decision = _gate_with_bounds(bounds).validate(
        Action(id="a", robot="arm_1", capability="move", params={"x": 0.0})
    )

    assert decision.ok is False
    assert decision.code == "safety.constraints.satisfied"
    check = next(item for item in decision.checks if item.code == decision.code)
    assert check.status == "rejected"
    assert check.evidence["error_type"] == "ConstraintConfigurationError"
    assert check.evidence["reason"] == expected_reason


def test_malformed_axis_bounds_reject_even_when_parameter_is_absent():
    decision = _gate_with_bounds({"unused_axis": [0.0]}).validate(
        Action(id="a", robot="arm_1", capability="move", params={})
    )

    assert decision.ok is False
    assert decision.code == "safety.constraints.satisfied"
    check = next(item for item in decision.checks if item.code == decision.code)
    assert check.evidence["reason"] == "axis_bounds_invalid_shape"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_bounded_parameter_is_structurally_rejected(value):
    decision = _gate_with_bounds({"x": [-1.0, 1.0]}).validate(
        Action(id="a", robot="arm_1", capability="move", params={"x": value})
    )

    assert decision.ok is False
    assert decision.code == "safety.constraints.satisfied"
    check = next(item for item in decision.checks if item.code == decision.code)
    assert check.status == "rejected"
    assert check.evidence["error_type"] == "ConstraintTypeError"
    assert check.evidence["reason"] == "parameter_not_finite"
    assert check.evidence["value"] in {"NaN", "Infinity", "-Infinity"}


def test_watch_default_timeout_is_checked_when_capability_has_no_override():
    gate = _gate()
    gate.default_action_timeout_s = 45.0
    gate.safety_rules["max_action_timeout_s"] = 30

    decision = gate.validate(
        Action(id="a", robot="arm_1", capability="move_to", params={"x": 0})
    )

    assert decision.ok is False
    assert decision.code == "safety.timeout.allowed"
    check = next(item for item in decision.checks if item.code == decision.code)
    assert check.evidence["timeout_s"] == 45.0
    assert check.evidence["timeout_source"] == "watch_default"
