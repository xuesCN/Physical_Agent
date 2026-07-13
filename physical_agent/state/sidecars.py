from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import threading
from typing import Any

from physical_agent.protocol.markdown import (
    extract_yaml_block_after_heading,
    fenced_yaml,
    parse_front_matter,
    render_front_matter,
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

SAFETY_SCHEMA = "physical-agent/safety/v1"
LOG_SCHEMA = "physical-agent/log/v1"

_LOG_LOCKS: dict[Path, threading.Lock] = {}
_LOG_LOCKS_GUARD = threading.Lock()


def _log_lock(path: Path) -> threading.Lock:
    key = path.resolve()
    with _LOG_LOCKS_GUARD:
        lock = _LOG_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _LOG_LOCKS[key] = lock
        return lock


class StateSidecars:
    """File adapters retained beside the SQLite runtime state."""

    filenames = SIDECAR_FILENAMES

    def __init__(self, workspace_path: str | Path):
        self.path = Path(workspace_path).resolve()

    def file(self, name: str) -> Path:
        return self.path / self.filenames[name]

    @property
    def safety_path(self) -> Path:
        return self.file("safety")

    @property
    def log_path(self) -> Path:
        return self.file("log")

    def initialize(self, *, overwrite: bool = False) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        if overwrite or not self.safety_path.exists():
            self.write_safety()
        if overwrite or not self.log_path.exists():
            self.log_path.write_text(_render_initial_log(), encoding="utf-8")

    def write_safety(self, rules: dict[str, Any] | None = None) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        target = self.safety_path
        target.write_text(
            _render_safety(rules, revision=self._next_revision(target)),
            encoding="utf-8",
        )

    def read_safety(self) -> dict[str, Any]:
        doc = parse_front_matter(self.safety_path.read_text(encoding="utf-8"))
        return {
            "metadata": doc.metadata,
            "rules": extract_yaml_block_after_heading(doc.body, "Rules", level=2) or {},
        }

    def append_log(self, message: str, *, actor: str | None = None) -> None:
        target = self.log_path
        with _log_lock(target):
            if target.exists():
                doc = parse_front_matter(target.read_text(encoding="utf-8"))
                metadata = dict(doc.metadata)
                body = doc.body.rstrip() + "\n\n"
                metadata["revision"] = doc.revision + 1
            else:
                metadata = {"schema": LOG_SCHEMA, "owner": "system", "revision": 1}
                body = "# Physical Agent Log\n\n"
            timestamp = (
                datetime.now(UTC)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )
            prefix = f"**{actor}**: " if actor else ""
            body += f"## {timestamp}\n\n{prefix}{message}\n"
            target.write_text(render_front_matter(metadata, body), encoding="utf-8")

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

    @staticmethod
    def _next_revision(target: Path) -> int:
        if not target.exists():
            return 1
        try:
            return parse_front_matter(target.read_text(encoding="utf-8")).revision + 1
        except Exception:
            return 1


def _render_safety(rules: dict[str, Any] | None = None, *, revision: int = 1) -> str:
    policy = dict(DEFAULT_SAFETY_RULES)
    if rules:
        policy.update(rules)
    return render_front_matter(
        {"schema": SAFETY_SCHEMA, "owner": "human", "revision": revision},
        "# Safety Policy\n\n## Rules\n\n" f"{fenced_yaml(policy)}\n",
    )


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
