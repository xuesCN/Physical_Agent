from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints


NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _preserve_nonblank_text(value: str) -> str:
    if not value.strip():
        raise ValueError("text must contain a non-whitespace character")
    return value


NonBlankText = Annotated[
    str,
    StringConstraints(min_length=1),
    AfterValidator(_preserve_nonblank_text),
]


class LLMContract(BaseModel):
    """Strict, closed contract for data authored by an LLM.

    These models are deliberately separate from the permissive persisted
    protocol models.  They are the single source for both provider JSON Schema
    and local Pydantic validation.
    """

    model_config = ConfigDict(extra="forbid", strict=True)


class LLMSafetyIntent(LLMContract):
    """Advisory cognition only; never a SafetyGate result."""

    hazards: list[str] = Field(default_factory=list, max_length=20)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    requested_evidence: list[str] = Field(default_factory=list, max_length=20)
    mitigations: list[str] = Field(default_factory=list, max_length=20)


class LLMActionMetadata(LLMContract):
    # F4 deliberately treats malformed expected checks as diagnostic metadata:
    # protocol normalization turns them into deterministic ``skipped`` results
    # instead of making an otherwise valid action fail.  ``Any`` preserves that
    # established boundary and also makes provider strict mode honestly
    # unavailable for the aggregate action schema.
    expected: Any | None = None
    safety_intent: LLMSafetyIntent | None = None


class LLMActionIntent(LLMContract):
    robot: NonEmptyText
    capability: NonEmptyText
    params: dict[str, Any]
    reason: NonEmptyText
    depends_on: list[str | int]
    metadata: LLMActionMetadata | None = None


class ChatLLMResponse(LLMContract):
    # Reply text is streamed before whole-object validation, so validation must
    # never trim or otherwise mutate bytes already shown to the consumer.
    reply: NonBlankText
    intent: Literal["chat", "inspect", "act", "remember"]
    steps: list[str]
    actions: list[LLMActionIntent]
    memory: list[str]
    refusal_reason: str | None = None


class PlannerLLMResponse(LLMContract):
    actions: list[LLMActionIntent]
    refusal_reason: str | None = None


CHAT_RESPONSE_SCHEMA: dict[str, Any] = ChatLLMResponse.model_json_schema()
ACTION_PLAN_SCHEMA: dict[str, Any] = PlannerLLMResponse.model_json_schema()


__all__ = [
    "ACTION_PLAN_SCHEMA",
    "CHAT_RESPONSE_SCHEMA",
    "ChatLLMResponse",
    "LLMActionIntent",
    "PlannerLLMResponse",
]
