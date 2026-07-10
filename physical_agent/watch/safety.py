from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real
from typing import Any, Literal

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from physical_agent.protocol.agent_output import SafetyCheckResult, safety_check_specs
from physical_agent.protocol.schemas import Action, Capability, RobotRuntimeProfile


@dataclass(frozen=True)
class SafetyDecision:
    ok: bool
    message: str = ""
    code: str = "safety.accepted"
    outcome: Literal["allow", "deny"] = "allow"
    checks: tuple[SafetyCheckResult, ...] = ()

    def __post_init__(self) -> None:
        # Preserve sensible semantics for third-party code that still creates
        # the legacy two-argument SafetyDecision(False, message) form.
        if not self.ok and self.outcome == "allow":
            object.__setattr__(self, "outcome", "deny")
        if not self.ok and self.code == "safety.accepted":
            object.__setattr__(self, "code", "safety.rejected")


class SafetyGate:
    """Watch-side safety gate for every physical action."""

    def __init__(
        self,
        *,
        robots: dict[str, RobotRuntimeProfile],
        safety_rules: dict[str, Any] | None = None,
        completed_action_ids: set[str] | None = None,
        executed_action_ids: set[str] | None = None,
        default_action_timeout_s: float = 30.0,
    ):
        self.robots = robots
        self.safety_rules = safety_rules or {}
        self.completed_action_ids = completed_action_ids or set()
        self.executed_action_ids = executed_action_ids or set()
        self.default_action_timeout_s = default_action_timeout_s

    def validate(self, action: Action) -> SafetyDecision:
        checks: list[SafetyCheckResult] = []

        def passed(code: str, message: str, **evidence: Any) -> None:
            checks.append(
                SafetyCheckResult(
                    code=code,
                    status="passed",
                    message=message,
                    evidence=evidence,
                )
            )

        def skipped(code: str, message: str, **evidence: Any) -> None:
            checks.append(
                SafetyCheckResult(
                    code=code,
                    status="skipped",
                    message=message,
                    evidence=evidence,
                )
            )

        def rejected(code: str, message: str, **evidence: Any) -> SafetyDecision:
            checks.append(
                SafetyCheckResult(
                    code=code,
                    status="rejected",
                    message=message,
                    evidence=evidence,
                )
            )
            completed_codes = {check.code for check in checks}
            for spec in safety_check_specs():
                if spec.code not in completed_codes:
                    skipped(
                        spec.code,
                        f"Skipped because {code} rejected the action.",
                        blocked_by=code,
                    )
            return SafetyDecision(
                False,
                message,
                code=code,
                outcome="deny",
                checks=tuple(checks),
            )

        if self.safety_rules.get("forbid_duplicate_action_ids", True):
            if action.id in self.executed_action_ids:
                return rejected(
                    "safety.action_id.unique",
                    f"Duplicate action id rejected: {action.id}",
                    action_id=action.id,
                )
            passed(
                "safety.action_id.unique",
                "Action id has not previously reached a terminal result.",
                action_id=action.id,
            )
        else:
            skipped(
                "safety.action_id.unique",
                "Duplicate action id checking is disabled by policy.",
                action_id=action.id,
            )

        unmet_dependencies = [
            dependency
            for dependency in action.depends_on
            if dependency not in self.completed_action_ids
        ]
        if unmet_dependencies:
            dependency = unmet_dependencies[0]
            return rejected(
                "safety.dependencies.completed",
                f"Action {action.id} waits for unmet dependency: {dependency}",
                dependencies=list(action.depends_on),
                unmet=unmet_dependencies,
            )
        passed(
            "safety.dependencies.completed",
            "All action dependencies are completed.",
            dependencies=list(action.depends_on),
        )

        robot = self.robots.get(action.robot)
        if robot is None:
            return rejected(
                "safety.robot.known",
                f"Unknown robot: {action.robot}",
                robot=action.robot,
            )
        passed(
            "safety.robot.known",
            "Robot is present in watch's live registry.",
            robot=action.robot,
            status=robot.status,
        )

        if robot.status not in {"connected", "ready"}:
            return rejected(
                "safety.robot.ready",
                f"Robot is not ready for execution: {action.robot} ({robot.status})",
                robot=action.robot,
                status=robot.status,
            )
        passed(
            "safety.robot.ready",
            "Watch connection and heartbeat state permit new execution work.",
            robot=action.robot,
            status=robot.status,
        )

        capability = _find_capability(robot.capabilities, action.capability)
        if capability is None:
            return rejected(
                "safety.capability.known",
                f"Robot {action.robot} does not expose capability: {action.capability}",
                robot=action.robot,
                capability=action.capability,
            )
        passed(
            "safety.capability.known",
            "Capability is published by the live driver.",
            robot=action.robot,
            capability=action.capability,
        )

        autonomous = self.safety_rules.get("allow_autonomous_execution", True)
        if not autonomous:
            return rejected(
                "safety.autonomy.allowed",
                "Autonomous execution is disabled by SAFETY.md",
                allow_autonomous_execution=False,
            )
        passed(
            "safety.autonomy.allowed",
            "Autonomous execution is allowed by SAFETY.md.",
            allow_autonomous_execution=True,
        )

        approval_required = capability.requires_approval or (
            robot.requires_approval and self.safety_rules.get(
                "require_human_approval_for_real_hardware", True
            )
        )
        approval_status = _approval_status(action)
        if approval_required and not _has_human_approval(action):
            subject = (
                f"Capability requires approved human approval: {capability.name}"
                if capability.requires_approval
                else f"Robot requires approved human approval: {action.robot}"
            )
            return rejected(
                "safety.approval.satisfied",
                subject,
                required=True,
                status=approval_status,
            )
        passed(
            "safety.approval.satisfied",
            (
                "Required human approval is present."
                if approval_required
                else "Human approval is not required."
            ),
            required=approval_required,
            status=approval_status,
        )

        schema_error = _params_schema_error(action, capability)
        if schema_error is not None:
            message, evidence = schema_error
            return rejected("safety.params.schema", message, **evidence)
        passed(
            "safety.params.schema",
            "Action parameters match the capability schema.",
            capability=action.capability,
        )

        constraint_error = _constraint_error(action, capability)
        if constraint_error is not None:
            message, evidence = constraint_error
            return rejected("safety.constraints.satisfied", message, **evidence)
        passed(
            "safety.constraints.satisfied",
            "Capability constraints are satisfied.",
            capability=action.capability,
        )

        timeout_s = (
            float(capability.timeout_s)
            if capability.timeout_s is not None
            else float(self.default_action_timeout_s)
        )
        timeout_source = (
            "capability" if capability.timeout_s is not None else "watch_default"
        )
        max_timeout = self.safety_rules.get("max_action_timeout_s")
        try:
            timeout_exceeds_policy = (
                timeout_s is not None
                and max_timeout is not None
                and timeout_s > max_timeout
            )
        except (TypeError, ValueError):
            return rejected(
                "safety.timeout.allowed",
                "Safety timeout policy cannot be compared with capability timeout.",
                timeout_s=timeout_s,
                timeout_source=timeout_source,
                max_action_timeout_s=max_timeout,
            )
        if timeout_exceeds_policy:
            return rejected(
                "safety.timeout.allowed",
                f"Capability timeout {timeout_s}s exceeds safety max {max_timeout}s",
                timeout_s=timeout_s,
                timeout_source=timeout_source,
                max_action_timeout_s=max_timeout,
            )
        passed(
            "safety.timeout.allowed",
            "Capability timeout is within the safety policy.",
            timeout_s=timeout_s,
            timeout_source=timeout_source,
            max_action_timeout_s=max_timeout,
        )

        return SafetyDecision(
            True,
            "Action accepted by watch safety gate.",
            code="safety.accepted",
            outcome="allow",
            checks=tuple(checks),
        )


def _find_capability(capabilities: list[Capability], name: str) -> Capability | None:
    for capability in capabilities:
        if capability.name == name:
            return capability
    return None


def _has_human_approval(action: Action) -> bool:
    metadata = action.metadata if isinstance(action.metadata, dict) else {}
    approval = metadata.get("approval")
    return bool(isinstance(approval, dict) and approval.get("status") == "approved")


def _approval_status(action: Action) -> str:
    metadata = action.metadata if isinstance(action.metadata, dict) else {}
    approval = metadata.get("approval")
    if not isinstance(approval, dict):
        return "not_required"
    return str(approval.get("status") or "pending")


def _params_schema_error(
    action: Action,
    capability: Capability,
) -> tuple[str, dict[str, Any]] | None:
    try:
        Draft202012Validator(capability.params_schema).validate(action.params)
    except ValidationError as exc:
        path = ".".join(str(part) for part in exc.path)
        detail = f" at {path}" if path else ""
        return (
            f"Invalid params for {action.capability}{detail}: {exc.message}",
            {
                "capability": action.capability,
                "path": path,
                "validator": str(exc.validator),
            },
        )
    except Exception as exc:
        return (
            f"Capability parameter schema could not be evaluated: {type(exc).__name__}: {exc}",
            {
                "capability": action.capability,
                "error_type": type(exc).__name__,
            },
        )
    return None


def _constraint_error(
    action: Action,
    capability: Capability,
) -> tuple[str, dict[str, Any]] | None:
    if "bounds" not in capability.constraints:
        return None

    bounds = capability.constraints["bounds"]
    if not isinstance(bounds, dict):
        return (
            "Capability constraints.bounds must be an object mapping parameters "
            "to [minimum, maximum].",
            {
                "capability": capability.name,
                "reason": "bounds_not_object",
                "configured_type": type(bounds).__name__,
                "error_type": "ConstraintConfigurationError",
            },
        )

    for axis, limit in bounds.items():
        if not isinstance(limit, (list, tuple)) or len(limit) != 2:
            return (
                f"Configured bounds for {axis} must contain exactly [minimum, maximum].",
                {
                    "capability": capability.name,
                    "axis": axis,
                    "reason": "axis_bounds_invalid_shape",
                    "configured_type": type(limit).__name__,
                    "configured_length": (
                        len(limit) if isinstance(limit, (list, tuple)) else None
                    ),
                    "error_type": "ConstraintConfigurationError",
                },
            )

        lower, upper = limit
        for endpoint, bound in (("minimum", lower), ("maximum", upper)):
            number_error = _finite_real_error(bound)
            if number_error == "not_numeric":
                return (
                    f"Configured {endpoint} bound for {axis} must be numeric.",
                    {
                        "capability": capability.name,
                        "axis": axis,
                        "endpoint": endpoint,
                        "value": _constraint_evidence_value(bound),
                        "reason": "bound_not_numeric",
                        "error_type": "ConstraintConfigurationError",
                    },
                )
            if number_error == "not_finite":
                return (
                    f"Configured {endpoint} bound for {axis} must be finite.",
                    {
                        "capability": capability.name,
                        "axis": axis,
                        "endpoint": endpoint,
                        "value": _constraint_evidence_value(bound),
                        "reason": "bound_not_finite",
                        "error_type": "ConstraintConfigurationError",
                    },
                )

        if lower > upper:
            return (
                f"Configured minimum bound for {axis} exceeds its maximum bound.",
                {
                    "capability": capability.name,
                    "axis": axis,
                    "lower": lower,
                    "upper": upper,
                    "reason": "bounds_inverted",
                    "error_type": "ConstraintConfigurationError",
                },
            )

        if axis not in action.params:
            continue

        value = action.params[axis]
        value_error = _finite_real_error(value)
        if value_error == "not_numeric":
            return (
                f"Param {axis} must be numeric before bounds can be enforced.",
                {
                    "axis": axis,
                    "value": _constraint_evidence_value(value),
                    "lower": lower,
                    "upper": upper,
                    "reason": "parameter_not_numeric",
                    "error_type": "ConstraintTypeError",
                },
            )
        if value_error == "not_finite":
            return (
                f"Param {axis} must be finite before bounds can be enforced.",
                {
                    "axis": axis,
                    "value": _constraint_evidence_value(value),
                    "lower": lower,
                    "upper": upper,
                    "reason": "parameter_not_finite",
                    "error_type": "ConstraintTypeError",
                },
            )
        if value < lower or value > upper:
            return (
                f"Param {axis}={value} is outside allowed bounds [{lower}, {upper}]",
                {
                    "axis": axis,
                    "value": value,
                    "lower": lower,
                    "upper": upper,
                    "reason": "parameter_out_of_bounds",
                },
            )
    return None


def _finite_real_error(value: Any) -> Literal["not_numeric", "not_finite"] | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return "not_numeric"
    try:
        if not math.isfinite(value):
            return "not_finite"
    except (OverflowError, TypeError, ValueError):
        return "not_finite"
    return None


def _constraint_evidence_value(value: Any) -> Any:
    """Keep rejection evidence serializable even for NaN/Inf or exotic values."""

    if isinstance(value, float) and not math.isfinite(value):
        if math.isnan(value):
            return "NaN"
        return "Infinity" if value > 0 else "-Infinity"
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return repr(value)
