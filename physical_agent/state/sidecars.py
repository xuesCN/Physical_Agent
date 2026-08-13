from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable, Mapping
from uuid import uuid4

from physical_agent.protocol.markdown import (
    fenced_yaml,
    parse_front_matter,
    render_front_matter,
)
from physical_agent.state.safety_policy import (
    SAFETY_OWNER,
    SAFETY_POLICY_MISSING,
    SAFETY_SCHEMA,
    SafetyPolicyError,
    SafetyPolicySnapshot,
    parse_safety_policy,
    validate_safety_rules,
)


SIDECAR_FILENAMES = {
    "safety": "SAFETY.md",
    "log": "LOG.md",
}

DEFAULT_SAFETY_RULES = {
    "require_human_approval_for_real_hardware": True,
    "allow_autonomous_execution": True,
    "max_action_timeout_s": 30,
    "forbid_duplicate_action_ids": True,
}

LOG_SCHEMA = "physical-agent/log/v1"


class StateSidecars:
    """File adapters retained beside the SQLite runtime state."""

    filenames = SIDECAR_FILENAMES

    def __init__(
        self,
        workspace_path: str | Path,
        *,
        safety_template_path: str | Path | None = None,
    ):
        self.path = Path(workspace_path).resolve()
        self.safety_template_path = (
            Path(safety_template_path).resolve()
            if safety_template_path is not None
            else None
        )

    def file(self, name: str) -> Path:
        return self.path / self.filenames[name]

    @property
    def safety_path(self) -> Path:
        return self.file("safety")

    @property
    def log_path(self) -> Path:
        return self.file("log")

    def initialize(
        self,
        *,
        overwrite: bool = False,
        create_safety_if_missing: bool = True,
        preserved_safety: SafetyPolicySnapshot | None = None,
    ) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        if overwrite and preserved_safety is not None:
            self._write_safety_document(
                DEFAULT_SAFETY_RULES,
                revision=preserved_safety.hard.revision + 1,
                agent_guidance=preserved_safety.agent_guidance,
            )
        elif self.safety_path.exists():
            snapshot = self.read_safety_snapshot()
            if overwrite:
                self._write_safety_document(
                    DEFAULT_SAFETY_RULES,
                    revision=snapshot.hard.revision + 1,
                    agent_guidance=snapshot.agent_guidance,
                )
        elif create_safety_if_missing:
            template = self._read_safety_template()
            self._write_safety_document(
                template.hard.rules if template is not None else DEFAULT_SAFETY_RULES,
                revision=1,
                agent_guidance=(
                    template.agent_guidance if template is not None else None
                ),
            )
        else:
            raise SafetyPolicyError(
                SAFETY_POLICY_MISSING,
                f"Missing SAFETY policy file: {self.safety_path}",
            )
        if overwrite or not self.log_path.exists():
            self.log_path.write_text(_render_initial_log(), encoding="utf-8")

    def write_safety(self, rules: dict[str, Any] | None = None) -> None:
        snapshot = self.read_safety_snapshot()
        policy = dict(DEFAULT_SAFETY_RULES)
        if rules:
            policy.update(rules)
        self._write_safety_document(
            policy,
            revision=snapshot.hard.revision + 1,
            agent_guidance=snapshot.agent_guidance,
        )

    def read_safety(self) -> dict[str, Any]:
        return self.read_safety_snapshot().to_dict()

    def read_safety_snapshot(self) -> SafetyPolicySnapshot:
        try:
            text = self.safety_path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise SafetyPolicyError(
                SAFETY_POLICY_MISSING,
                f"Missing SAFETY policy file: {self.safety_path}",
            ) from exc
        return parse_safety_policy(text, source=str(self.safety_path))

    def _read_safety_template(self) -> SafetyPolicySnapshot | None:
        template_path = self.safety_template_path
        if template_path is None or not template_path.exists():
            return None
        if not template_path.is_file():
            raise SafetyPolicyError(
                SAFETY_POLICY_MISSING,
                f"SAFETY template is not a file: {template_path}",
            )
        return parse_safety_policy(
            template_path.read_text(encoding="utf-8"),
            source=str(template_path),
        )

    def _write_safety_document(
        self,
        rules: Mapping[str, Any],
        *,
        revision: int,
        agent_guidance: str | None,
    ) -> None:
        validated_rules = validate_safety_rules(dict(rules))
        _atomic_write_text(
            self.safety_path,
            _render_safety(
                validated_rules,
                revision=revision,
                agent_guidance=agent_guidance,
            ),
        )

    def write_log_snapshot(
        self,
        *,
        metadata: Mapping[str, Any],
        entries: Iterable[Mapping[str, Any]],
    ) -> None:
        target = self.log_path
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        rendered = _render_log_snapshot(metadata=metadata, entries=entries)
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(rendered)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def validate_log(self, *, expected_revision: int) -> dict[str, Any]:
        doc = parse_front_matter(self.log_path.read_text(encoding="utf-8"))
        if doc.schema != LOG_SCHEMA:
            raise ValueError(
                f"LOG.md schema must be `{LOG_SCHEMA}`, got `{doc.schema}`."
            )
        if doc.revision != expected_revision:
            raise ValueError(
                "LOG.md mirror revision does not match SQLite log revision: "
                f"file={doc.revision}, sqlite={expected_revision}."
            )
        return dict(doc.metadata)

def _render_safety(
    rules: Mapping[str, Any],
    *,
    revision: int = 1,
    agent_guidance: str | None = None,
) -> str:
    body = "# Safety Policy\n\n## Rules\n\n" f"{fenced_yaml(dict(rules))}\n"
    if agent_guidance and agent_guidance.strip():
        body += f"\n## Agent Guidance\n\n{agent_guidance.strip()}\n"
    return render_front_matter(
        {"schema": SAFETY_SCHEMA, "owner": SAFETY_OWNER, "revision": revision},
        body,
    )


def _atomic_write_text(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _render_initial_log() -> str:
    # Preserve the initialized SQLite workspace format byte-for-byte. The
    # first append normalizes it through render_front_matter as before.
    return (
        "---\n"
        f"schema: {LOG_SCHEMA}\n"
        "owner: system\n"
        "revision: 1\n"
        "---\n"
        "# Physical Agent Log\n"
    )


def _render_log_snapshot(
    *,
    metadata: Mapping[str, Any],
    entries: Iterable[Mapping[str, Any]],
) -> str:
    sections = ["# Physical Agent Log\n"]
    for entry in entries:
        actor = entry.get("actor")
        prefix = f"**{actor}**: " if actor else ""
        sections.append(f"\n## {entry['ts']}\n\n{prefix}{entry['message']}\n")
    return render_front_matter(dict(metadata), "".join(sections))
