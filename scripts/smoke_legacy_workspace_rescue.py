#!/usr/bin/env python3
"""Exercise the documented legacy Markdown rescue path against a real checkout."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import site
import subprocess
import sys
import tempfile
from typing import Any

import yaml


HISTORICAL_COMMIT = "9072b4e9fb600e505668aeb6076eb6cb85e5ff82"
ROOT = Path(__file__).resolve().parents[1]


OLD_SETUP_AND_MIGRATE = r'''
import hashlib
import json
import os
from pathlib import Path
import sys

import physical_agent
from physical_agent.cli import app
from physical_agent.config import write_default_config
from physical_agent.protocol.workspace import Workspace
from typer.testing import CliRunner
import yaml

project = Path(os.environ["PA_RESCUE_PROJECT"])
result_path = Path(os.environ["PA_RESCUE_OLD_RESULT"])
config_path = write_default_config(project / "physical-agent.yaml", overwrite=True)
config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
config["workspace"]["backend"] = "markdown"
config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

workspace = Workspace(project / "workspace")
workspace.initialize()
workspace.write_task("legacy rescue task", ["preserve every data surface"])
workspace.write_capabilities(
    {
        "legacy_arm": {
            "kind": "arm",
            "driver": "mock_arm",
            "status": "connected",
            "capabilities": [
                {
                    "name": "observe",
                    "description": "Observe legacy state.",
                    "params_schema": {"type": "object"},
                }
            ],
        }
    }
)
workspace.write_world(
    {
        "summary": "legacy world summary",
        "robots": {"legacy_arm": {"status": "ready"}},
        "objects": {"legacy_block": {"location": "legacy_table"}},
        "environment": {"mode": "rescue"},
        "artifacts": ["legacy-artifact.txt"],
        "raw": {"source": "9072b4e"},
    }
)
workspace.write_actions(
    pending=[
        {
            "id": "act_legacy_pending",
            "robot": "legacy_arm",
            "capability": "observe",
            "reason": "pending rescue action",
        }
    ],
    completed=[
        {
            "id": "act_legacy_completed",
            "robot": "legacy_arm",
            "capability": "observe",
            "reason": "completed rescue action",
        }
    ],
    cancelled=[
        {
            "id": "act_legacy_cancelled",
            "robot": "legacy_arm",
            "capability": "observe",
            "reason": "cancelled rescue action",
        }
    ],
)
feedback = {
    "action_id": "act_legacy_completed",
    "status": "completed",
    "robot": "legacy_arm",
    "capability": "observe",
    "message": "legacy feedback retained",
}
workspace.write_feedback(feedback, [feedback])
workspace.write_safety(
    {
        "allow_autonomous_execution": False,
        "max_action_timeout_s": 11,
    }
)
workspace.write_chat(
    [
        {"role": "user", "content": "legacy chat question"},
        {"role": "assistant", "content": "legacy chat answer"},
    ],
    running_summary="legacy running summary",
    compact=False,
)
workspace.write_plan(
    {
        "status": "proposed_actions",
        "intent": "rescue",
        "summary": "legacy plan summary",
        "steps": ["migrate", "verify"],
        "actions": [
            {
                "id": "act_legacy_pending",
                "robot": "legacy_arm",
                "capability": "observe",
            }
        ],
        "needs_watch": True,
    }
)
workspace.write_memory(
    [
        {
            "content": "legacy memory retained",
            "source": "test",
            "kind": "lesson",
            "tags": ["rescue", "legacy"],
            "importance": 7,
            "created_at": "2026-07-13T00:00:00Z",
        }
    ]
)
workspace.append_upload_metadata(
    {
        "original_path": "/legacy/input.txt",
        "original_name": "input.txt",
        "stored_path": str(workspace.uploads_path / "legacy-input.txt"),
        "stored_name": "legacy-input.txt",
        "sha256": "legacy-sha256",
        "size_bytes": 12,
        "content_type": "text/plain",
        "status": "stored",
    }
)
workspace.append_log("legacy log retained", actor="legacy-operator")

config_before = config_path.read_text(encoding="utf-8")
safety_before = workspace.file("safety").read_text(encoding="utf-8")
log_before = workspace.file("log").read_text(encoding="utf-8")
runner = CliRunner()
migration = runner.invoke(
    app,
    ["migrate-md-to-sqlite", "--config", str(config_path)],
)
if migration.exit_code != 0:
    raise RuntimeError(f"historical migration failed: {migration.output}\n{migration.exception}")
if config_path.read_text(encoding="utf-8") != config_before:
    raise AssertionError("historical migrator changed physical-agent.yaml")

second = runner.invoke(
    app,
    ["migrate-md-to-sqlite", "--config", str(config_path)],
)
if second.exit_code == 0 or "already exists" not in second.output:
    raise AssertionError("historical migrator did not protect an existing state.db")

result_path.write_text(
    json.dumps(
        {
            "python": sys.executable,
            "physical_agent_file": str(Path(physical_agent.__file__).resolve()),
            "config_unchanged": True,
            "existing_db_refused_without_overwrite": True,
            "migration_output": migration.output,
            "safety_sha256": hashlib.sha256(safety_before.encode()).hexdigest(),
            "log_sha256": hashlib.sha256(log_before.encode()).hexdigest(),
        },
        indent=2,
        sort_keys=True,
    ) + "\n",
    encoding="utf-8",
)
'''


CURRENT_INIT_AND_VERIFY = r'''
import hashlib
import json
import os
from pathlib import Path
import sys

import physical_agent
from physical_agent.cli import app
from physical_agent.state import open_state_store
from typer.testing import CliRunner

project = Path(os.environ["PA_RESCUE_PROJECT"])
result_path = Path(os.environ["PA_RESCUE_CURRENT_RESULT"])
old_result = json.loads(Path(os.environ["PA_RESCUE_OLD_RESULT"]).read_text(encoding="utf-8"))
config_path = project / "physical-agent.yaml"
workspace_path = project / "workspace"
safety_before = (workspace_path / "SAFETY.md").read_text(encoding="utf-8")
log_before = (workspace_path / "LOG.md").read_text(encoding="utf-8")

runner = CliRunner()
initialized = runner.invoke(app, ["init", "--config", str(config_path)])
if initialized.exit_code != 0:
    raise RuntimeError(f"current init failed: {initialized.output}\n{initialized.exception}")
checked = runner.invoke(app, ["state-check", "--config", str(config_path)])
if checked.exit_code != 0:
    raise RuntimeError(f"current state-check failed: {checked.output}\n{checked.exception}")
if "Workspace initialized: yes" not in checked.output:
    raise AssertionError(checked.output)
if "SQLite schema complete: yes" not in checked.output:
    raise AssertionError(checked.output)

store = open_state_store(config_path=config_path)
assert store.read_task()["task"] == "legacy rescue task"
assert "legacy_arm" in store.read_capabilities()["robots"]
world = store.read_world()
assert world["summary"] == "legacy world summary"
assert world["state"]["objects"]["legacy_block"]["location"] == "legacy_table"
actions = store.read_actions()
assert [item.id for item in actions["pending"]] == ["act_legacy_pending"]
assert [item.id for item in actions["completed"]] == ["act_legacy_completed"]
assert [item.id for item in actions["cancelled"]] == ["act_legacy_cancelled"]
assert store.read_feedback()["latest"]["message"] == "legacy feedback retained"
safety = store.read_safety()
assert safety["rules"]["allow_autonomous_execution"] is False
assert safety["rules"]["max_action_timeout_s"] == 11
chat = store.read_chat()
assert chat["running_summary"] == "legacy running summary"
assert [item.content for item in chat["messages"]] == [
    "legacy chat question",
    "legacy chat answer",
]
plan = store.read_plan()["plan"]
assert plan.summary == "legacy plan summary"
assert plan.steps == ["migrate", "verify"]
memory = store.read_memory()["notes"]
assert memory[0]["content"] == "legacy memory retained"
assert memory[0]["importance"] == 7
uploads = store.read_uploads()["uploads"]
assert uploads[0]["original_name"] == "input.txt"
audit_dir = Path(store.export_human_view()["out_dir"])
log = json.loads((audit_dir / "log.json").read_text(encoding="utf-8"))
assert log["entries"][0]["message"] == "legacy log retained"
assert (audit_dir / "SAFETY.md").read_text(encoding="utf-8") == safety_before

safety_after = (workspace_path / "SAFETY.md").read_text(encoding="utf-8")
log_after = (workspace_path / "LOG.md").read_text(encoding="utf-8")
assert hashlib.sha256(safety_after.encode()).hexdigest() == old_result["safety_sha256"]
assert hashlib.sha256(log_after.encode()).hexdigest() == old_result["log_sha256"]

result_path.write_text(
    json.dumps(
        {
            "python": sys.executable,
            "physical_agent_file": str(Path(physical_agent.__file__).resolve()),
            "init_output": initialized.output,
            "state_check_output": checked.output,
            "all_data_surfaces_verified": True,
            "sidecars_preserved_by_non_force_init": True,
        },
        indent=2,
        sort_keys=True,
    ) + "\n",
    encoding="utf-8",
)
'''


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def _venv_python(venv_path: Path) -> Path:
    if os.name == "nt":
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"


def _dependency_paths() -> list[str]:
    candidates = [*site.getsitepackages(), site.getusersitepackages()]
    return [str(Path(item).resolve()) for item in candidates if Path(item).exists()]


def run_rescue_smoke(*, repo_root: Path, keep_temp: bool = False) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    _run(["git", "cat-file", "-e", f"{HISTORICAL_COMMIT}^{{commit}}"], cwd=repo_root)

    root = Path(tempfile.mkdtemp(prefix="physical-agent-r3c-"))
    checkout = root / "legacy-checkout"
    project = root / "project"
    old_venv = root / "legacy-venv"
    old_result_path = root / "old-result.json"
    current_result_path = root / "current-result.json"
    worktree_added = False
    try:
        _run(
            ["git", "worktree", "add", "--detach", str(checkout), HISTORICAL_COMMIT],
            cwd=repo_root,
        )
        worktree_added = True
        _run(
            [sys.executable, "-m", "venv", "--without-pip", str(old_venv)],
            cwd=repo_root,
        )
        old_python = _venv_python(old_venv)
        project.mkdir(parents=True)

        shared_env = os.environ.copy()
        shared_env.update(
            {
                "PA_RESCUE_PROJECT": str(project),
                "PA_RESCUE_OLD_RESULT": str(old_result_path),
                "PA_RESCUE_CURRENT_RESULT": str(current_result_path),
            }
        )
        old_env = dict(shared_env)
        old_env["PYTHONPATH"] = os.pathsep.join(
            [str(checkout), *_dependency_paths()]
        )
        _run(
            [str(old_python), "-c", OLD_SETUP_AND_MIGRATE],
            cwd=project,
            env=old_env,
        )

        config_path = project / "physical-agent.yaml"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if config["workspace"]["backend"] != "markdown":
            raise AssertionError("historical migrator unexpectedly changed the backend")
        config["workspace"]["backend"] = "sqlite"
        config_path.write_text(
            yaml.safe_dump(config, sort_keys=False),
            encoding="utf-8",
        )

        current_env = dict(shared_env)
        current_env.pop("PYTHONPATH", None)
        _run(
            [sys.executable, "-c", CURRENT_INIT_AND_VERIFY],
            cwd=repo_root,
            env=current_env,
        )

        old_result = json.loads(old_result_path.read_text(encoding="utf-8"))
        current_result = json.loads(current_result_path.read_text(encoding="utf-8"))
        old_package = Path(old_result["physical_agent_file"])
        current_package = Path(current_result["physical_agent_file"])
        if checkout not in old_package.parents:
            raise AssertionError(f"old package was not loaded from worktree: {old_package}")
        if repo_root not in current_package.parents:
            raise AssertionError(
                f"current package was not loaded from current checkout: {current_package}"
            )
        if old_result["python"] == current_result["python"]:
            raise AssertionError("old and current checks used the same interpreter path")

        return {
            "ok": True,
            "historical_commit": HISTORICAL_COMMIT,
            "temporary_root": str(root),
            "old": old_result,
            "current": current_result,
        }
    finally:
        if worktree_added:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(checkout)],
                cwd=repo_root,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            subprocess.run(
                ["git", "worktree", "prune"],
                cwd=repo_root,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        if not keep_temp:
            shutil.rmtree(root, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--keep-temp", action="store_true")
    args = parser.parse_args()

    result = run_rescue_smoke(repo_root=args.repo, keep_temp=args.keep_temp)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.json_out:
        args.json_out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
