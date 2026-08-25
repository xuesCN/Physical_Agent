from __future__ import annotations

import pytest
from pydantic import ValidationError

from physical_agent.agent.llm_contracts import (
    ACTION_PLAN_SCHEMA,
    CHAT_RESPONSE_SCHEMA,
    ChatLLMResponse,
    PlannerLLMResponse,
)
from physical_agent.llm.openai_compatible import _strict_schema_compatible
from physical_agent.protocol.expectations import evaluate_expected


def test_llm_contract_schemas_have_one_pydantic_source() -> None:
    assert CHAT_RESPONSE_SCHEMA == ChatLLMResponse.model_json_schema()
    assert ACTION_PLAN_SCHEMA == PlannerLLMResponse.model_json_schema()
    assert _strict_schema_compatible(CHAT_RESPONSE_SCHEMA) is False
    assert _strict_schema_compatible(ACTION_PLAN_SCHEMA) is False


def test_chat_schema_describes_clarification_and_memory_scope() -> None:
    properties = CHAT_RESPONSE_SCHEMA["properties"]
    actions = properties["actions"]
    memory = properties["memory"]

    assert actions["type"] == "array"
    assert "Use an empty list" in actions["description"]
    assert "missing or ambiguous" in actions["description"]
    assert "instead of guessing" in actions["description"]
    assert memory["type"] == "array"
    assert "user explicitly asked to remember" in memory["description"]
    assert "Use an empty list otherwise" in memory["description"]
    assert "when allowed, include one or more concise notes" in memory["description"]
    assert "current-turn requests" in memory["description"]
    assert "approval, or refusal events" in memory["description"]
    assert "safety overrides" in memory["description"]
    assert {"actions", "memory"}.issubset(CHAT_RESPONSE_SCHEMA["required"])


def test_chat_contract_accepts_explicit_durable_memory_note() -> None:
    parsed = ChatLLMResponse.model_validate(
        {
            "reply": "I will remember that preference.",
            "intent": "remember",
            "steps": [],
            "actions": [],
            "memory": ["The user always prefers human approval before execution."],
        }
    )

    assert parsed.memory == [
        "The user always prefers human approval before execution."
    ]


@pytest.mark.parametrize(
    "schema",
    [
        {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
            "anyOf": [
                {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                    "additionalProperties": False,
                }
            ],
        },
        {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
            "allOf": [
                {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                    "additionalProperties": False,
                }
            ],
        },
        {
            "type": "object",
            "properties": {
                "value": {"type": "string", "not": {"const": "forbidden"}}
            },
            "required": ["value"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
            "dependentRequired": {"value": ["other"]},
        },
    ],
)
def test_strict_schema_preflight_rejects_unsupported_composition(schema: dict) -> None:
    assert _strict_schema_compatible(schema) is False


def test_chat_reply_validation_preserves_streamed_whitespace() -> None:
    parsed = ChatLLMResponse.model_validate(
        {
            "reply": " hello\n",
            "intent": "chat",
            "steps": [],
            "actions": [],
            "memory": [],
        }
    )

    assert parsed.reply == " hello\n"


def test_planner_contract_forbids_unknown_action_fields() -> None:
    payload = {
        "actions": [
            {
                "robot": "arm_1",
                "capability": "observe",
                "params": {},
                "reason": "Inspect the workspace.",
                "depends_on": [],
                "surprise": "must not be silently ignored",
            }
        ]
    }

    with pytest.raises(ValidationError, match="extra_forbidden"):
        PlannerLLMResponse.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"actions": [], "unexpected": "top-level drift"},
        {
            "actions": [
                {
                    "robot": "arm_1",
                    "capability": "observe",
                    "params": {},
                    "reason": "Inspect the workspace.",
                    "depends_on": [],
                    "metadata": {"source": "provider-authored provenance is forbidden"},
                }
            ]
        },
    ],
)
def test_planner_contract_forbids_unknown_top_level_and_metadata_fields(
    payload: dict,
) -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        PlannerLLMResponse.model_validate(payload)


def test_malformed_expected_remains_diagnostic_and_becomes_skipped() -> None:
    payload = {
        "actions": [
            {
                "robot": "arm_1",
                "capability": "observe",
                "params": {},
                "reason": "Inspect the workspace.",
                "depends_on": [],
                "metadata": {
                    "expected": [
                        {"op": "unknown", "extension": "preserved for diagnostics"}
                    ],
                    "safety_intent": {"hazards": ["pinch point"]},
                },
            }
        ]
    }

    parsed = PlannerLLMResponse.model_validate(payload)
    expected = parsed.model_dump(mode="json")["actions"][0]["metadata"]["expected"]
    result = evaluate_expected(expected, world={})

    assert result["status"] == "skipped"
    assert result["expected"][0]["extension"] == "preserved for diagnostics"
    assert (
        parsed.model_dump(mode="json")["actions"][0]["metadata"]["safety_intent"][
            "hazards"
        ]
        == ["pinch point"]
    )
