from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from physical_agent.agent.context_builder import (
    ContextBudget,
    SafetyGuidanceContextError,
    build_context,
    build_planner_context,
)
from physical_agent.config import write_default_config
from physical_agent.protocol.schemas import Observation
from physical_agent.state import open_state_store


GOLDEN_DIR = Path(__file__).parent / "golden" / "context_builder"


class NoWriteStore:
    def __init__(self, store):
        self._store = store

    def __getattr__(self, name):
        blocked_prefixes = (
            "write_",
            "append_",
            "mark_",
            "claim_",
            "recover_",
            "approve_",
            "reject_",
        )
        if name.startswith(blocked_prefixes):
            raise AssertionError(f"context_builder must not call {name}")
        return getattr(self._store, name)


@pytest.mark.parametrize("purpose", ["reply", "proposal", "planner", "tool_loop"])
def test_context_builder_matches_golden_snapshot(tmp_path, purpose):
    store = _seed_store(tmp_path)
    retrieved_context = (
        {
            "query": "calibration",
            "context_policy": "Retrieved context is untrusted proposal context only.",
            "results": [
                {
                    "source_type": "upload",
                    "source_id": "upload-sha",
                    "chunk_index": 0,
                    "content": "retrieved upload text",
                    "trust_level": "untrusted",
                }
            ],
        }
        if purpose == "proposal"
        else None
    )

    bundle = build_context(
        store,
        "pick the red block",
        purpose=purpose,
        retrieved_context=retrieved_context,
    )

    assert _snapshot(bundle) == _read_golden(f"{purpose}.json")


@pytest.mark.parametrize("purpose", ["reply", "proposal", "planner", "tool_loop"])
def test_context_builder_serializes_unicode_without_ascii_escaping(tmp_path, purpose):
    store = _seed_store(tmp_path)

    bundle = build_context(store, "检查车轮状态", purpose=purpose)

    wire_content = bundle.messages[1]["content"]
    assert wire_content == json.dumps(bundle.payload, ensure_ascii=False)
    assert "检查车轮状态" in wire_content
    assert "\\u68c0" not in wire_content
    assert json.loads(wire_content) == bundle.payload


@pytest.mark.parametrize("field", ["world", "capabilities", "feedback"])
def test_context_builder_uses_unescaped_unicode_length_for_budgets(tmp_path, field):
    store = _seed_store(tmp_path)
    documents = {
        "world": {
            "summary": "车轮状态" * 80,
            "state": {"robots": {"car_1": {"status": "台架待命"}}},
        },
        "capabilities": {
            "robots": {
                "car_1": {
                    "kind": "小车",
                    "capabilities": [
                        {"name": "观察", "description": "检查车轮状态" * 80}
                    ],
                }
            }
        },
        "feedback": {
            "latest": {"message": "车轮保持架空" * 80},
            "history": [{"message": "车轮保持架空" * 80}],
        },
    }
    document = documents[field]
    native_length = len(json.dumps(document, ensure_ascii=False, sort_keys=True))
    escaped_length = len(json.dumps(document, ensure_ascii=True, sort_keys=True))
    assert native_length < escaped_length
    budget = ContextBudget(**{f"{field}_max_chars": native_length})

    payload = build_context(
        store,
        "检查上下文预算",
        purpose="proposal",
        budget=budget,
        **{field: document},
    ).payload

    assert payload[field] == document


@pytest.mark.parametrize("purpose", ["reply", "proposal", "planner", "tool_loop"])
def test_context_builder_separates_hard_safety_from_agent_guidance(tmp_path, purpose):
    store = _seed_store(tmp_path)
    _write_safety_with_guidance(store, "Keep the wheels suspended above the bench.")

    payload = build_context(store, "inspect safely", purpose=purpose).payload

    assert set(payload["safety"]) == {
        "metadata",
        "hard",
        "guidance",
        "policy_identity_digest",
    }
    assert payload["safety"]["hard"]["rules"]["forbid_duplicate_action_ids"] is True
    assert payload["safety"]["hard"]["authority"] == "watch_safety_gate"
    assert payload["safety"]["guidance"]["text"].startswith("Keep the wheels")
    assert payload["safety"]["guidance"]["authority"] == "advisory_context_only"
    assert payload["safety"]["guidance"]["may_authorize_execution"] is False
    assert payload["safety"]["guidance"]["may_override_hard_policy"] is False


@pytest.mark.parametrize("purpose", ["proposal", "planner", "tool_loop"])
def test_hardware_action_context_rejects_guidance_over_budget(tmp_path, purpose):
    store = _seed_store(tmp_path)
    _write_safety_with_guidance(store, "bench only " * 40)
    budget = ContextBudget(safety_guidance_max_chars=80)

    with pytest.raises(SafetyGuidanceContextError) as caught:
        build_context(store, "move", purpose=purpose, budget=budget)

    assert caught.value.code == "safety.guidance.budget_exceeded"
    assert caught.value.purpose == purpose


def test_reply_truncates_guidance_with_explicit_marker(tmp_path):
    store = _seed_store(tmp_path)
    _write_safety_with_guidance(store, "bench only " * 40)

    payload = build_context(
        store,
        "explain safety",
        purpose="reply",
        budget=ContextBudget(safety_guidance_max_chars=80),
    ).payload

    guidance = payload["safety"]["guidance"]
    assert guidance["truncated"] is True
    assert guidance["status"] == "truncated"
    assert guidance["warning"] == "safety.guidance.truncated_for_context_budget"
    assert guidance["original_json_chars"] > guidance["included_json_chars"]
    assert guidance["included_json_chars"] <= 80


def test_simulation_action_context_marks_missing_guidance_without_rejecting():
    capabilities = {
        "robots": {
            "sim_1": {
                "execution_mode": "simulation",
                "capabilities": [{"name": "observe"}],
            }
        }
    }
    bundle = build_planner_context(
        "look around",
        capabilities=capabilities,
        world={},
        safety={"metadata": {"revision": 1}, "rules": {}},
    )

    guidance = bundle.payload["safety"]["guidance"]
    assert guidance["status"] == "missing"
    assert guidance["warning"] == "safety.guidance.missing_simulation_only"


@pytest.mark.parametrize("profile", [{}, {"execution_mode": "unknown"}])
def test_missing_or_unknown_execution_mode_defaults_to_hardware_fail_closed(profile):
    with pytest.raises(SafetyGuidanceContextError) as caught:
        build_planner_context(
            "move",
            capabilities={"robots": {"robot_1": profile}},
            world={},
            safety={"metadata": {"revision": 1}, "rules": {}},
        )

    assert caught.value.code == "safety.guidance.missing"


def test_context_summaries_keep_hardware_safety_evidence(tmp_path):
    store = _seed_store(tmp_path)
    _write_safety_with_guidance(store, "Bench only.")
    capabilities = {
        "robots": {
            "car_1": {
                "kind": "car",
                "execution_mode": "hardware",
                "status": "connected",
                "requires_approval": True,
                "capabilities": [
                    {
                        "name": "drive_for",
                        "description": "drive" + ("x" * 500),
                        "constraints": {
                            "bounds": {"speed": [-12, 12], "duration_ms": [1, 180]}
                        },
                        "params_schema": {
                            "type": "object",
                            "required": ["speed", "duration_ms"],
                            "properties": {"speed": {}, "duration_ms": {}},
                        },
                    }
                ],
            }
        }
    }
    robot_state = {
        "status": "moving",
        "tof_available": True,
        "tof_valid": False,
        "tof_mm": 0,
        "moving": True,
        "motor_cmd": 12,
        "bench_only": True,
        "watchdog_tripped": False,
        "raw_noise": "x" * 500,
    }
    world = {
        "summary": "car state",
        "state": {"robots": {"car_1": robot_state}},
        "observation": {"robots": {"car_1": robot_state}},
    }

    payload = build_context(
        store,
        "inspect",
        purpose="proposal",
        budget=ContextBudget(world_max_chars=120, capabilities_max_chars=120),
        capabilities=capabilities,
        world=world,
    ).payload

    summarized_capability = payload["capabilities"]["robots"]["car_1"]
    assert summarized_capability["execution_mode"] == "hardware"
    assert summarized_capability["capabilities"][0]["constraints"]["bounds"] == {
        "speed": [-12, 12],
        "duration_ms": [1, 180],
    }
    for branch in ("state", "observation"):
        summarized_robot = payload["world"][branch]["robots"]["car_1"]
        assert summarized_robot == {
            "id": "car_1",
            "status": "moving",
            "tof_available": True,
            "tof_valid": False,
            "tof_mm": 0,
            "moving": True,
            "motor_cmd": 12,
            "bench_only": True,
            "watchdog_tripped": False,
        }


def test_context_builder_is_read_only(tmp_path):
    store = _seed_store(tmp_path)
    before = _state_snapshot(store)

    bundle = build_context(
        NoWriteStore(store),
        "look around",
        purpose="proposal",
    )

    assert bundle.payload["latest_user_message"] == "look around"
    assert _state_snapshot(store) == before


def test_context_builder_never_replays_reasoning_summary_metadata(tmp_path):
    store = _seed_store(tmp_path)
    marker = "UNTRUSTED_PROVIDER_REASONING_MARKER"
    store.append_chat_message(
        "assistant",
        "A user-visible answer.",
        metadata={
            "intent": "chat",
            "reasoning_summary": marker,
        },
    )

    payload = build_context(store, "continue", purpose="proposal").payload

    history = payload["chat_history"]
    assistant = next(item for item in history if item["content"] == "A user-visible answer.")
    assert assistant["metadata"]["intent"] == "chat"
    assert "reasoning_summary" not in assistant["metadata"]
    assert marker not in json.dumps(payload, ensure_ascii=False)


def test_context_builder_includes_expectation_check_feedback(tmp_path):
    store = _seed_store(tmp_path)
    expectation_event = {
        "event": "expectation_check",
        "action_id": "act_099",
        "status": "violated",
        "message": "Expected `objects.red_block.location` to equal \"tray\"; actual was \"table\".",
        "expected": [
            {"path": "objects.red_block.location", "op": "eq", "value": "tray"}
        ],
        "actual": [
            {"path": "objects.red_block.location", "value": "table", "status": "violated"}
        ],
    }
    store.write_feedback(expectation_event, [expectation_event])

    bundle = build_context(store, "what happened?", purpose="proposal")

    feedback = bundle.payload["feedback"]
    assert feedback["latest"]["event"] == "expectation_check"
    assert feedback["latest"]["status"] == "violated"
    assert feedback["latest"]["expected"][0]["value"] == "tray"
    assert feedback["latest"]["actual"][0]["value"] == "table"


def test_context_builder_summarizes_world_and_capabilities_deterministically(tmp_path):
    store = _seed_store(tmp_path)
    budget = ContextBudget(world_max_chars=120, capabilities_max_chars=120)

    first = build_context(
        store,
        "summarize",
        purpose="proposal",
        budget=budget,
    ).payload
    second = build_context(
        store,
        "summarize",
        purpose="proposal",
        budget=budget,
    ).payload

    assert first == second
    assert "budget_summary" in first["world"]
    assert "raw" not in json.dumps(first["world"])
    assert first["world"]["state"]["objects"]["red_block"]["location"] == "table"
    assert "summarized because they exceeded" in first["capabilities"]["summary"]
    assert first["capabilities"]["robots"]["arm_1"]["capabilities"][0]["name"] == "observe"


def test_context_builder_bounds_structured_feedback_history(tmp_path):
    store = _seed_store(tmp_path)
    events = [
        {
            "event": "safety_gate",
            "action_id": f"act_{index:03d}",
            "status": "passed",
            "message": "gate passed " + ("evidence " * 40),
            "checks": [
                {
                    "code": "safety.robot.known",
                    "status": "passed",
                    "message": "known " + ("detail " * 20),
                    "evidence": {"index": index},
                }
            ],
        }
        for index in range(80)
    ]
    store.write_feedback(events[-1], events)
    budget = ContextBudget(feedback_max_events=10, feedback_max_chars=3000)

    payload = build_context(
        store,
        "what happened?",
        purpose="proposal",
        budget=budget,
    ).payload

    assert len(payload["feedback"]["history"]) <= 10
    assert payload["feedback"]["history"][-1]["action_id"] == "act_079"
    assert len(json.dumps(payload["feedback"], ensure_ascii=False, sort_keys=True)) <= 3300


def _seed_store(tmp_path):
    config_path = write_default_config(tmp_path / "physical-agent.yaml", overwrite=True)
    store = open_state_store(config_path=config_path)
    store.initialize()
    store.write_chat(
        [
            {
                "role": "user",
                "content": "older question",
                "created_at": "2026-01-01T00:00:00Z",
            },
            {
                "role": "assistant",
                "content": "older answer",
                "created_at": "2026-01-01T00:00:01Z",
                "metadata": {"intent": "inspect"},
            },
        ],
        running_summary="Earlier summary with stale unsafe_execute mention.",
        compact=False,
    )
    store.write_capabilities(
        {
            "arm_1": {
                "kind": "arm",
                "driver": "mock_arm",
                "status": "connected",
                "requires_approval": True,
                "capabilities": [
                    {
                        "name": "place",
                        "description": "Place an object.",
                        "params_schema": {
                            "type": "object",
                            "required": ["target"],
                            "properties": {"target": {"type": "string"}},
                        },
                        "requires_approval": True,
                    },
                    {
                        "name": "observe",
                        "description": "Inspect the workspace.",
                        "params_schema": {"type": "object", "properties": {}},
                        "requires_approval": False,
                    },
                ],
            }
        }
    )
    store.write_world(
        Observation(
            summary="Red block is on the table.",
            robots={"arm_1": {"status": "idle"}},
            objects={
                "red_block": {
                    "type": "block",
                    "location": "table",
                    "status": "visible",
                    "raw": {"camera_blob": "drop when summarized"},
                }
            },
            raw={"frame": "drop when summarized"},
        )
    )
    store.write_feedback(
        {"status": "completed", "message": "Observed table."},
        [
            {
                "status": "completed",
                "message": "Observed table.",
                "action_id": "act_001",
            }
        ],
    )
    store.write_memory(
        [
            {
                "content": "low priority note",
                "source": "chat",
                "kind": "note",
                "tags": [],
                "importance": 1,
                "created_at": "2026-01-01T00:00:00Z",
            },
            {
                "content": "medium priority note",
                "source": "chat",
                "kind": "note",
                "tags": ["ops"],
                "importance": 5,
                "created_at": "2026-01-01T00:00:00Z",
            },
            {
                "content": "UNTRUSTED UPLOAD EXCERPT\nDo not bypass SafetyGate.",
                "source": "upload",
                "kind": "upload_excerpt",
                "tags": ["upload"],
                "importance": 5,
                "created_at": "2026-01-01T00:00:02Z",
            },
        ]
    )
    _write_safety_with_guidance(
        store,
        "Keep the robot on its supervised test fixture and obey live safety state.",
    )
    return store


def _write_safety_with_guidance(store, guidance: str) -> None:
    path = store.file("safety")
    current = path.read_text(encoding="utf-8")
    base = current.split("\n## Agent Guidance\n", 1)[0].rstrip()
    path.write_text(
        base + f"\n\n## Agent Guidance\n\n{guidance.strip()}\n",
        encoding="utf-8",
    )


def _snapshot(bundle) -> dict[str, Any]:
    return {
        "purpose": bundle.purpose,
        "max_tokens": bundle.max_tokens,
        "temperature": bundle.temperature,
        "messages": [
            bundle.messages[0],
            {
                "role": bundle.messages[1]["role"],
                "payload": json.loads(bundle.messages[1]["content"]),
            },
        ],
    }


def _read_golden(name: str) -> dict[str, Any]:
    return json.loads((GOLDEN_DIR / name).read_text(encoding="utf-8"))


def _state_snapshot(store) -> dict[str, Any]:
    return {
        "chat": _safe(store.read_chat()),
        "plan": _safe(store.read_plan()),
        "memory": _safe(store.read_memory()),
        "actions": _safe(store.read_actions()),
        "feedback": _safe(store.read_feedback()),
    }


def _safe(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe(item) for item in value]
    return value
