from __future__ import annotations

import os
from pathlib import Path
import sqlite3
from typing import Any

from physical_agent.config import PhysicalAgentConfig
from physical_agent.state.factory import open_state_store
from physical_agent.state.sqlite import (
    ACTION_CLAIM_COLUMNS,
    MEMORY_NOTE_COLUMNS,
    SQLITE_SCHEMA_TABLES,
    SqliteStateStore,
    UPLOAD_METADATA_COLUMNS,
)


def run_state_check(
    config: PhysicalAgentConfig,
    *,
    base_dir: str | Path,
) -> dict[str, Any]:
    """Inspect state backend readiness without initializing or mutating state."""

    root = Path(base_dir).resolve()
    backend = (config.workspace.backend or "sqlite").strip().lower()
    workspace = open_state_store(config, base_dir=root)
    initialized = workspace.exists()
    audit_dir = workspace.path / "audit"
    audit_parent = audit_dir if audit_dir.exists() else audit_dir.parent
    result: dict[str, Any] = {
        "backend": backend,
        "workspace_path": str(workspace.path),
        "workspace_initialized": initialized,
        "audit_dir": str(audit_dir),
        "audit_export_writable": _path_writable(audit_parent),
        "sqlite_schema_complete": None,
        "sqlite_missing_tables": [],
        "sqlite_missing_action_columns": [],
        "sqlite_missing_memory_columns": [],
        "sqlite_missing_upload_columns": [],
    }
    if isinstance(workspace, SqliteStateStore):
        result.update(_sqlite_schema_status(workspace.db_path))
    return result


def state_check_ok(result: dict[str, Any]) -> bool:
    if not result.get("workspace_initialized"):
        return False
    if not result.get("audit_export_writable"):
        return False
    sqlite_complete = result.get("sqlite_schema_complete")
    if sqlite_complete is False:
        return False
    return True


def _sqlite_schema_status(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {
            "sqlite_schema_complete": False,
            "sqlite_missing_tables": sorted(SQLITE_SCHEMA_TABLES),
            "sqlite_missing_action_columns": sorted(ACTION_CLAIM_COLUMNS),
            "sqlite_missing_memory_columns": sorted(MEMORY_NOTE_COLUMNS),
            "sqlite_missing_upload_columns": sorted(UPLOAD_METADATA_COLUMNS),
        }
    try:
        with sqlite3.connect(db_path) as conn:
            table_rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            tables = {str(row[0]) for row in table_rows}
            action_columns: set[str] = set()
            if "actions" in tables:
                action_columns = {
                    str(row[1])
                    for row in conn.execute("PRAGMA table_info(actions)").fetchall()
                }
            memory_columns: set[str] = set()
            if "memory_notes" in tables:
                memory_columns = {
                    str(row[1])
                    for row in conn.execute("PRAGMA table_info(memory_notes)").fetchall()
                }
            upload_columns: set[str] = set()
            if "upload_metadata" in tables:
                upload_columns = {
                    str(row[1])
                    for row in conn.execute("PRAGMA table_info(upload_metadata)").fetchall()
                }
    except sqlite3.Error:
        return {
            "sqlite_schema_complete": False,
            "sqlite_missing_tables": sorted(SQLITE_SCHEMA_TABLES),
            "sqlite_missing_action_columns": sorted(ACTION_CLAIM_COLUMNS),
            "sqlite_missing_memory_columns": sorted(MEMORY_NOTE_COLUMNS),
            "sqlite_missing_upload_columns": sorted(UPLOAD_METADATA_COLUMNS),
        }

    missing_tables = sorted(SQLITE_SCHEMA_TABLES - tables)
    missing_action_columns = sorted(set(ACTION_CLAIM_COLUMNS) - action_columns)
    missing_memory_columns = sorted(set(MEMORY_NOTE_COLUMNS) - memory_columns)
    missing_upload_columns = sorted(set(UPLOAD_METADATA_COLUMNS) - upload_columns)
    return {
        "sqlite_schema_complete": not missing_tables
        and not missing_action_columns
        and not missing_memory_columns
        and not missing_upload_columns,
        "sqlite_missing_tables": missing_tables,
        "sqlite_missing_action_columns": missing_action_columns,
        "sqlite_missing_memory_columns": missing_memory_columns,
        "sqlite_missing_upload_columns": missing_upload_columns,
    }


def _path_writable(path: Path) -> bool:
    return path.exists() and path.is_dir() and os.access(path, os.W_OK)
