from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from pydantic import ConfigDict, Field, model_validator

from physical_agent.protocol.expectations import normalize_expected_metadata
from physical_agent.protocol.schemas import Action, StrictModel


ACTION_METADATA_SCHEMA = "physical-agent/action-metadata/v1"
ApprovalStatus = Literal["not_required", "pending", "approved", "rejected"]
SAFETY_INTENT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "hazards": {"type": "array", "maxItems": 20, "items": {"type": "string"}},
        "assumptions": {"type": "array", "maxItems": 20, "items": {"type": "string"}},
        "requested_evidence": {
            "type": "array",
            "maxItems": 20,
            "items": {"type": "string"},
        },
        "mitigations": {"type": "array", "maxItems": 20, "items": {"type": "string"}},
    },
}


class SafetyIntent(StrictModel):
    """Advisory safety reasoning proposed by cognition, never a Gate result."""

    hazards: list[str] = Field(default_factory=list, max_length=20)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    requested_evidence: list[str] = Field(default_factory=list, max_length=20)
    mitigations: list[str] = Field(default_factory=list, max_length=20)


class ActionApproval(StrictModel):
    """Typed view of the approval record stored in ``Action.metadata``."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    required: bool = False
    status: ApprovalStatus = "not_required"
    by: str | None = None
    at: str | None = None
    reason: str | None = None
    approved_by: str | None = None
    approved_at: str | None = None
    rejected_by: str | None = None
    rejected_at: str | None = None

    @model_validator(mode="after")
    def normalize_status(self) -> "ActionApproval":
        if self.required and self.status == "not_required":
            self.status = "pending"
        elif not self.required and self.status == "pending":
            self.status = "not_required"
        return self


class ActionCorrelation(StrictModel):
    """Identifier shared by actions created from one proposal operation."""

    session_id: str = "workspace"
    proposal_id: str

    @classmethod
    def create(
        cls,
        *,
        session_id: str = "workspace",
        proposal_id: str | None = None,
    ) -> "ActionCorrelation":
        return cls(
            session_id=session_id,
            proposal_id=proposal_id or _identifier("proposal"),
        )


class ProposalContext(StrictModel):
    """Trusted provenance added by an application-layer proposal boundary."""

    source: str
    proposed_by: str
    original_task: str | None = None
    user_message: str | None = None
    draft_reason: str | None = None
    planner_reason: str | None = None
    correlation: ActionCorrelation = Field(default_factory=ActionCorrelation.create)


class ActionMetadata(StrictModel):
    """Typed contract for known action metadata while preserving extensions.

    SQLite continues to store metadata as JSON for backwards compatibility.
    New code should parse it through this model instead of guessing dictionary
    shapes. Unknown extension fields are intentionally retained.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    schema_: str = Field(default=ACTION_METADATA_SCHEMA, alias="schema")
    source: str | None = None
    proposed_by: str | None = None
    original_task: str | None = None
    user_message: str | None = None
    draft_reason: str | None = None
    planner_reason: str | None = None
    correlation: ActionCorrelation | None = None
    approval: ActionApproval | None = None
    safety_intent: SafetyIntent | None = None
    expected: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def schema(self) -> str:
        return self.schema_


def parse_action_metadata(metadata: dict[str, Any] | None) -> ActionMetadata:
    """Return the typed view of an action's known metadata fields."""

    normalized = normalize_expected_metadata(metadata)
    normalized.setdefault("schema", ACTION_METADATA_SCHEMA)
    return ActionMetadata.model_validate(normalized)


def with_proposal_metadata(
    action: Action | dict[str, Any],
    context: ProposalContext,
    *,
    trust_approval: bool = False,
) -> Action:
    """Apply trusted provenance without changing the Action wire shape.

    Proposal callers are not approval authorities. By default any caller-
    supplied approval decision is removed before the action reaches the state
    store; the action-board approval methods remain the only mutation path.
    """

    parsed = action if isinstance(action, Action) else Action.model_validate(action)
    data = parsed.model_dump(mode="json")
    metadata = dict(data.get("metadata") or {})
    if not trust_approval:
        metadata.pop("approval", None)

    metadata["schema"] = ACTION_METADATA_SCHEMA
    for name in (
        "source",
        "proposed_by",
        "original_task",
        "user_message",
        "draft_reason",
        "planner_reason",
    ):
        value = getattr(context, name)
        if value is None:
            # These keys describe proposal provenance. An ingress caller may
            # provide content fields such as ``expected``, but it may not
            # smuggle trusted provenance through an unset context field.
            metadata.pop(name, None)
        else:
            metadata[name] = value

    metadata["correlation"] = context.correlation.model_dump(
        mode="json",
        exclude_none=True,
    )

    contract = parse_action_metadata(metadata)
    data["metadata"] = contract.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
        exclude_unset=True,
    )
    return Action.model_validate(data)


def _identifier(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:20]}"
