from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Any, Mapping, TypeAlias

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode

from physical_agent.protocol.markdown import (
    FRONT_MATTER_RE,
    extract_markdown_sections,
)


SAFETY_SCHEMA = "physical-agent/safety/v1"
SAFETY_OWNER = "human"
SAFETY_POLICY_MISSING = "safety.policy.missing"
SAFETY_POLICY_INVALID = "safety.policy.invalid"
MAX_AGENT_GUIDANCE_CHARS = 4000

SafetyRuleValue: TypeAlias = bool | int | float

_RULE_KEY_ORDER = (
    "require_human_approval_for_real_hardware",
    "allow_autonomous_execution",
    "max_action_timeout_s",
    "forbid_duplicate_action_ids",
)
_RULE_KEYS = frozenset(_RULE_KEY_ORDER)
_BOOLEAN_RULE_KEYS = _RULE_KEYS - {"max_action_timeout_s"}
_YAML_FENCE_RE = re.compile(
    r"^[ \t]{0,3}```yaml[ \t]*\r?\n(.*?)\r?\n[ \t]{0,3}```[ \t]*$",
    re.MULTILINE | re.DOTALL,
)


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects ambiguous duplicate mapping keys."""

    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[Any, Any]:
        if not isinstance(node, MappingNode):
            raise ConstructorError(
                None,
                None,
                f"expected a mapping node, but found {node.id}",
                node.start_mark,
            )
        self.flatten_mapping(node)
        mapping: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in mapping
            except TypeError as exc:
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "found an unhashable key",
                    key_node.start_mark,
                ) from exc
            if duplicate:
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"found duplicate key {key!r}",
                    key_node.start_mark,
                )
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _UniqueKeySafeLoader.construct_mapping,
)


class SafetyPolicyError(ValueError):
    """Stable, machine-classifiable SAFETY policy failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class HardSafetyPolicy:
    revision: int
    rules: Mapping[str, SafetyRuleValue]
    digest: str

    def __post_init__(self) -> None:
        if type(self.revision) is not int or self.revision <= 0:
            raise SafetyPolicyError(
                SAFETY_POLICY_INVALID,
                "Hard safety policy revision must be a positive integer.",
            )
        validated_rules = validate_safety_rules(
            dict(self.rules),
            source="HardSafetyPolicy",
        )
        expected_digest = _stable_json_digest(validated_rules)
        if self.digest != expected_digest:
            raise SafetyPolicyError(
                SAFETY_POLICY_INVALID,
                "Hard safety policy digest does not match its validated rules.",
            )
        object.__setattr__(self, "rules", MappingProxyType(validated_rules))


@dataclass(frozen=True)
class SafetyPolicySnapshot:
    metadata: Mapping[str, Any]
    hard: HardSafetyPolicy
    agent_guidance: str | None
    guidance_digest: str
    identity_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": dict(self.metadata),
            "rules": dict(self.hard.rules),
            "agent_guidance": self.agent_guidance,
            "hard_policy_digest": self.hard.digest,
            "guidance_digest": self.guidance_digest,
            "policy_identity_digest": self.identity_digest,
        }


def parse_safety_policy(
    text: str,
    *,
    source: str = "SAFETY.md",
) -> SafetyPolicySnapshot:
    try:
        front_matter_match = FRONT_MATTER_RE.match(text)
        if front_matter_match is None:
            raise ValueError(
                "SAFETY Markdown documents must start with YAML front matter."
            )
        metadata = yaml.load(
            front_matter_match.group(1),
            Loader=_UniqueKeySafeLoader,
        ) or {}
        if not isinstance(metadata, dict):
            raise ValueError("SAFETY front matter must be a YAML mapping.")
    except Exception as exc:
        raise SafetyPolicyError(
            SAFETY_POLICY_INVALID,
            f"{source} has invalid front matter: {exc}",
        ) from exc

    metadata = dict(metadata)
    if metadata.get("schema") != SAFETY_SCHEMA:
        raise SafetyPolicyError(
            SAFETY_POLICY_INVALID,
            f"{source} schema must be `{SAFETY_SCHEMA}`.",
        )
    if metadata.get("owner") != SAFETY_OWNER:
        raise SafetyPolicyError(
            SAFETY_POLICY_INVALID,
            f"{source} owner must be `{SAFETY_OWNER}`.",
        )
    revision = metadata.get("revision")
    if type(revision) is not int or revision <= 0:
        raise SafetyPolicyError(
            SAFETY_POLICY_INVALID,
            f"{source} revision must be a positive integer.",
        )

    body = front_matter_match.group(2)
    rules_sections = extract_markdown_sections(body, "Rules", level=2)
    if len(rules_sections) != 1:
        raise SafetyPolicyError(
            SAFETY_POLICY_INVALID,
            f"{source} must contain exactly one `## Rules` section.",
        )
    yaml_blocks = [match.group(1) for match in _YAML_FENCE_RE.finditer(rules_sections[0])]
    if len(yaml_blocks) != 1:
        raise SafetyPolicyError(
            SAFETY_POLICY_INVALID,
            f"{source} `## Rules` must contain exactly one in-section YAML block.",
        )
    try:
        raw_rules = yaml.load(yaml_blocks[0], Loader=_UniqueKeySafeLoader)
    except yaml.YAMLError as exc:
        raise SafetyPolicyError(
            SAFETY_POLICY_INVALID,
            f"{source} `## Rules` YAML is invalid: {exc}",
        ) from exc
    rules = validate_safety_rules(raw_rules, source=source)

    guidance_sections = extract_markdown_sections(
        body,
        "Agent Guidance",
        level=2,
    )
    if len(guidance_sections) > 1:
        raise SafetyPolicyError(
            SAFETY_POLICY_INVALID,
            f"{source} must not contain duplicate `## Agent Guidance` sections.",
        )
    guidance = _normalize_guidance(guidance_sections[0]) if guidance_sections else None
    return build_safety_snapshot(
        metadata=metadata,
        rules=rules,
        agent_guidance=guidance,
    )


def validate_safety_rules(
    value: Any,
    *,
    source: str = "SAFETY.md",
) -> dict[str, SafetyRuleValue]:
    if not isinstance(value, dict):
        raise SafetyPolicyError(
            SAFETY_POLICY_INVALID,
            f"{source} `## Rules` YAML must be a mapping.",
        )

    keys = set(value)
    missing = sorted(_RULE_KEYS - keys)
    unknown = sorted(keys - _RULE_KEYS, key=str)
    if missing:
        raise SafetyPolicyError(
            SAFETY_POLICY_INVALID,
            f"{source} `## Rules` is missing required keys: {', '.join(missing)}.",
        )
    if unknown:
        raise SafetyPolicyError(
            SAFETY_POLICY_INVALID,
            f"{source} `## Rules` contains unknown keys: "
            f"{', '.join(str(key) for key in unknown)}.",
        )

    for key in sorted(_BOOLEAN_RULE_KEYS):
        if type(value[key]) is not bool:
            raise SafetyPolicyError(
                SAFETY_POLICY_INVALID,
                f"{source} rule `{key}` must be a boolean.",
            )

    timeout = value["max_action_timeout_s"]
    if type(timeout) not in {int, float} or not math.isfinite(timeout) or timeout <= 0:
        raise SafetyPolicyError(
            SAFETY_POLICY_INVALID,
            f"{source} rule `max_action_timeout_s` must be a positive finite number.",
        )
    return {key: value[key] for key in _RULE_KEY_ORDER}


def build_safety_snapshot(
    *,
    metadata: Mapping[str, Any],
    rules: Mapping[str, Any],
    agent_guidance: str | None,
) -> SafetyPolicySnapshot:
    revision = metadata.get("revision")
    if type(revision) is not int or revision <= 0:
        raise SafetyPolicyError(
            SAFETY_POLICY_INVALID,
            "SAFETY.md revision must be a positive integer.",
        )
    validated_rules = validate_safety_rules(dict(rules))
    normalized_guidance = _normalize_guidance(agent_guidance)
    hard_digest = _stable_json_digest(validated_rules)
    guidance_digest = _text_digest(normalized_guidance or "")
    identity_digest = _stable_json_digest(
        {
            "revision": revision,
            "hard_policy_digest": hard_digest,
            "guidance_digest": guidance_digest,
        }
    )
    return SafetyPolicySnapshot(
        metadata=metadata,
        hard=HardSafetyPolicy(
            revision=revision,
            rules=validated_rules,
            digest=hard_digest,
        ),
        agent_guidance=normalized_guidance,
        guidance_digest=guidance_digest,
        identity_digest=identity_digest,
    )


def guidance_json_chars(text: str | None) -> int:
    """Measure guidance using the shared unescaped JSON wire character model."""

    return len(json.dumps(text or "", ensure_ascii=False))


def _normalize_guidance(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _stable_json_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
