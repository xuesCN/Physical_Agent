from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import multiprocessing
from pathlib import Path
import re
import sqlite3

import pytest

from physical_agent.config import write_default_config
from physical_agent.doctor import doctor_ok, run_doctor
from physical_agent.protocol.markdown import parse_front_matter
from physical_agent.state import SqliteStateStore, open_state_store
from physical_agent.state.sidecars import SIDECAR_FILENAMES, StateSidecars


DEFAULT_SAFETY_RULES = {
    "require_human_approval_for_real_hardware": True,
    "allow_autonomous_execution": True,
    "max_action_timeout_s": 30,
    "forbid_duplicate_action_ids": True,
}


def _append_log_from_spawned_process(
    workspace_path: str,
    message: str,
    start_barrier,
) -> None:
    start_barrier.wait(timeout=60)
    SqliteStateStore(workspace_path).append_log(message, actor="worker")


def _project(tmp_path: Path) -> tuple[Path, SqliteStateStore]:
    config_path = write_default_config(
        tmp_path / "physical-agent.yaml",
        overwrite=True,
    )
    store = open_state_store(config_path=config_path)
    assert isinstance(store, SqliteStateStore)
    store.initialize()
    return config_path, store


def _audit_json(store: SqliteStateStore, name: str) -> dict:
    out = Path(store.export_human_view()["out_dir"])
    return json.loads((out / f"{name}.json").read_text(encoding="utf-8"))


def test_sidecar_adapter_owns_only_safety_and_log_files(tmp_path):
    sidecars = StateSidecars(tmp_path / "workspace")

    assert SIDECAR_FILENAMES == {"safety": "SAFETY.md", "log": "LOG.md"}
    assert sidecars.filenames == SIDECAR_FILENAMES
    assert sidecars.safety_path.name == "SAFETY.md"
    assert sidecars.log_path.name == "LOG.md"
    with pytest.raises(KeyError):
        sidecars.file("task")


def test_sqlite_runtime_and_doctor_do_not_reference_full_workspace():
    project_root = Path(__file__).resolve().parents[1]
    for relative in ("physical_agent/state/sqlite.py", "physical_agent/doctor.py"):
        source = (project_root / relative).read_text(encoding="utf-8")
        assert "Workspace.filenames" not in source
        assert "_file_workspace" not in source


def test_safety_sidecar_defaults_override_front_matter_and_revision(tmp_path):
    _, store = _project(tmp_path)

    initial = store.read_safety()
    assert initial["rules"] == DEFAULT_SAFETY_RULES
    assert initial["metadata"] == {
        "schema": "physical-agent/safety/v1",
        "owner": "human",
        "revision": 1,
    }

    store.write_safety(
        {
            "allow_autonomous_execution": False,
            "max_action_timeout_s": 7,
        }
    )

    updated = store.read_safety()
    assert updated["rules"] == {
        **DEFAULT_SAFETY_RULES,
        "allow_autonomous_execution": False,
        "max_action_timeout_s": 7,
    }
    assert updated["metadata"]["revision"] == 2
    document = parse_front_matter(store.file("safety").read_text(encoding="utf-8"))
    assert document.schema == "physical-agent/safety/v1"
    assert document.owner == "human"
    assert document.revision == 2


def test_normal_init_preserves_sidecars_and_overwrite_restores_defaults(tmp_path):
    _, store = _project(tmp_path)
    store.write_safety({"allow_autonomous_execution": False})
    store.append_log("keep this operator note", actor="operator")
    safety_before = store.file("safety").read_text(encoding="utf-8")
    log_before = store.file("log").read_text(encoding="utf-8")

    store.initialize()

    assert store.file("safety").read_text(encoding="utf-8") == safety_before
    assert store.file("log").read_text(encoding="utf-8") == log_before

    store.initialize(overwrite=True)

    assert store.read_safety()["rules"] == DEFAULT_SAFETY_RULES
    reset_log = parse_front_matter(store.file("log").read_text(encoding="utf-8"))
    assert reset_log.schema == "physical-agent/log/v1"
    assert reset_log.revision == 1
    assert "keep this operator note" not in reset_log.body
    assert _audit_json(store, "log")["entries"] == []


def test_log_sidecar_initialization_actor_timestamp_revision_and_sqlite_mirror(tmp_path):
    _, store = _project(tmp_path)
    initial = parse_front_matter(store.file("log").read_text(encoding="utf-8"))
    assert initial.metadata == {
        "schema": "physical-agent/log/v1",
        "owner": "system",
        "revision": 1,
    }

    store.append_log("gripper opened", actor="watch")

    mirrored = parse_front_matter(store.file("log").read_text(encoding="utf-8"))
    assert mirrored.revision == 2
    assert "**watch**: gripper opened" in mirrored.body
    assert re.search(r"^## \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", mirrored.body, re.MULTILINE)
    assert store.validate_log_mirror()["revision"] == 2
    assert _audit_json(store, "log")["entries"][0]["message"] == "gripper opened"


def test_log_sidecar_concurrent_append_keeps_every_entry_and_revision(tmp_path):
    _, store = _project(tmp_path)
    messages = [f"parallel log {index}" for index in range(16)]

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda message: store.append_log(message, actor="worker"), messages))

    mirrored = parse_front_matter(store.file("log").read_text(encoding="utf-8"))
    assert mirrored.revision == 1 + len(messages)
    for message in messages:
        assert f"**worker**: {message}" in mirrored.body
    with sqlite3.connect(store.db_path) as conn:
        rows = conn.execute("SELECT actor, message FROM log_entries").fetchall()
    assert sorted(rows) == sorted(("worker", message) for message in messages)
    assert store.validate_log_mirror()["revision"] == 1 + len(messages)


def test_log_mirror_spawn_processes_preserve_all_entries_and_latest_revision(tmp_path):
    _, store = _project(tmp_path)
    process_count = 32
    messages = [
        f"spawned log {index:02d} " + (str(index % 10) * 50_000)
        for index in range(process_count)
    ]
    context = multiprocessing.get_context("spawn")
    start_barrier = context.Barrier(process_count + 1)
    processes = [
        context.Process(
            target=_append_log_from_spawned_process,
            args=(str(store.path), message, start_barrier),
        )
        for message in messages
    ]

    try:
        for process in processes:
            process.start()
        start_barrier.wait(timeout=60)
        for process in processes:
            process.join(timeout=60)
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=10)

    with sqlite3.connect(store.db_path) as conn:
        rows = conn.execute(
            "SELECT actor, message FROM log_entries ORDER BY id"
        ).fetchall()
        sqlite_revision = conn.execute(
            "SELECT revision FROM doc_state WHERE name = 'log'"
        ).fetchone()[0]
    assert sorted(rows) == sorted(("worker", message) for message in messages)
    assert sqlite_revision == 1 + process_count

    mirrored = parse_front_matter(store.file("log").read_text(encoding="utf-8"))
    assert mirrored.revision == sqlite_revision
    for message in messages:
        assert f"**worker**: {message}" in mirrored.body
    assert {process.exitcode for process in processes} == {0}


def test_log_mirror_write_failure_keeps_sqlite_truth_and_doctor_reports_stale_revision(
    tmp_path,
    monkeypatch,
):
    config_path, store = _project(tmp_path)
    log_path = store.file("log").resolve()
    real_open = Path.open

    def fail_log_write(path: Path, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        resolved = path.resolve()
        is_log_target = resolved == log_path
        is_log_temp = (
            resolved.parent == log_path.parent
            and path.name.startswith(f".{log_path.name}.")
        )
        if "w" in mode and (is_log_target or is_log_temp):
            raise OSError("simulated LOG mirror write failure")
        return real_open(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", fail_log_write)
        assert store.append_log("committed before mirror failure", actor="watch") is None

    log = _audit_json(store, "log")
    assert log["entries"][0]["message"] == "committed before mirror failure"
    failed = {check.name: check for check in run_doctor(config_path)}
    assert failed["workspace:log"].ok is False
    assert "file=1, sqlite=2" in failed["workspace:log"].message


def test_append_log_rebuilds_malformed_log_mirror_from_sqlite(tmp_path):
    config_path, store = _project(tmp_path)
    store.file("log").write_text("not front matter", encoding="utf-8")

    store.append_log("committed despite malformed mirror", actor="watch")

    log = _audit_json(store, "log")
    assert log["entries"][0]["message"] == "committed despite malformed mirror"
    mirrored = parse_front_matter(store.file("log").read_text(encoding="utf-8"))
    assert mirrored.revision == 2
    assert "**watch**: committed despite malformed mirror" in mirrored.body
    checks = {check.name: check for check in run_doctor(config_path)}
    assert checks["workspace:log"].ok is True


@pytest.mark.parametrize("name", ["safety", "log"])
def test_doctor_rejects_malformed_sidecar_and_checks_all_logical_documents(
    tmp_path,
    name,
):
    config_path, store = _project(tmp_path)
    healthy = {check.name: check for check in run_doctor(config_path)}
    assert doctor_ok(list(healthy.values()))
    assert {
        f"workspace:{document}" for document in store.filenames
    }.issubset(healthy)

    store.file(name).write_text("not front matter", encoding="utf-8")
    failed = {check.name: check for check in run_doctor(config_path)}

    assert failed[f"workspace:{name}"].ok is False
    assert "front matter" in failed[f"workspace:{name}"].message.lower()


def test_audit_copies_safety_file_but_reads_log_only_from_sqlite(tmp_path):
    _, store = _project(tmp_path)
    store.write_safety({"allow_autonomous_execution": False})
    store.append_log("database audit entry", actor="watch")
    safety_source = store.file("safety").read_text(encoding="utf-8")
    store.file("log").write_text(
        "---\nschema: physical-agent/log/v1\nowner: system\nrevision: 2\n---\n\n"
        "# Physical Agent Log\n\n## 2000-01-01T00:00:00Z\n\nforged mirror entry\n",
        encoding="utf-8",
    )

    result = store.export_human_view()
    out = Path(result["out_dir"])

    assert (out / "SAFETY.md").read_text(encoding="utf-8") == safety_source
    log = json.loads((out / "log.json").read_text(encoding="utf-8"))
    assert [entry["message"] for entry in log["entries"]] == ["database audit entry"]
    assert "forged mirror entry" not in (out / "log.json").read_text(encoding="utf-8")
