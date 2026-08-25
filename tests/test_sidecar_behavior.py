from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import multiprocessing
from pathlib import Path
import re
import sqlite3

import pytest
import yaml

from physical_agent.config import write_default_config
from physical_agent.doctor import doctor_ok, run_doctor
from physical_agent.protocol.markdown import parse_front_matter
from physical_agent.state import (
    HardSafetyPolicy,
    SafetyPolicyError,
    SqliteStateStore,
    open_state_store,
)
from physical_agent.state.safety_policy import (
    SAFETY_POLICY_INVALID,
    SAFETY_POLICY_MISSING,
)
from physical_agent.state.sidecars import SIDECAR_FILENAMES, StateSidecars


DEFAULT_SAFETY_RULES = {
    "require_human_approval_for_real_hardware": True,
    "allow_autonomous_execution": True,
    "max_action_timeout_s": 30,
    "forbid_duplicate_action_ids": True,
}

GUIDANCE = "Keep the wheels raised. Invalid TOF means distance is unknown."


def _safety_text(
    *,
    metadata: str = (
        "schema: physical-agent/safety/v1\n"
        "owner: human\n"
        "revision: 1"
    ),
    rules: str = (
        "require_human_approval_for_real_hardware: true\n"
        "allow_autonomous_execution: true\n"
        "max_action_timeout_s: 30\n"
        "forbid_duplicate_action_ids: true"
    ),
    guidance: str | None = GUIDANCE,
    after_rules: str = "",
) -> str:
    guidance_section = (
        f"\n\n## Agent Guidance\n\n{guidance}\n" if guidance is not None else "\n"
    )
    return (
        f"---\n{metadata}\n---\n\n"
        "# Safety Policy\n\n"
        f"## Rules\n\n```yaml\n{rules}\n```{after_rules}"
        f"{guidance_section}"
    )


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


def test_safety_snapshot_separates_hard_policy_guidance_and_digests(tmp_path):
    sidecars = StateSidecars(tmp_path / "workspace")
    sidecars.safety_path.parent.mkdir(parents=True)
    sidecars.safety_path.write_text(_safety_text(), encoding="utf-8")

    snapshot = sidecars.read_safety_snapshot()
    public = sidecars.read_safety()

    assert snapshot.hard.revision == 1
    assert dict(snapshot.hard.rules) == DEFAULT_SAFETY_RULES
    assert snapshot.agent_guidance == GUIDANCE
    assert snapshot.hard.digest == public["hard_policy_digest"]
    assert snapshot.guidance_digest == public["guidance_digest"]
    assert snapshot.identity_digest == public["policy_identity_digest"]
    assert public["agent_guidance"] == GUIDANCE


@pytest.mark.parametrize(
    ("revision", "rules", "digest", "message"),
    [
        pytest.param(0, DEFAULT_SAFETY_RULES, "forged", "positive integer", id="revision"),
        pytest.param(
            1,
            {**DEFAULT_SAFETY_RULES, "allow_autonomous_execution": "true"},
            "forged",
            "must be a boolean",
            id="rules",
        ),
        pytest.param(1, DEFAULT_SAFETY_RULES, "forged", "digest", id="digest"),
    ],
)
def test_hard_safety_policy_cannot_be_forged(revision, rules, digest, message):
    with pytest.raises(SafetyPolicyError, match=message) as exc_info:
        HardSafetyPolicy(revision=revision, rules=rules, digest=digest)

    assert exc_info.value.code == SAFETY_POLICY_INVALID


@pytest.mark.parametrize(
    ("text", "message"),
    [
        pytest.param(
            _safety_text(metadata="schema: wrong\nowner: human\nrevision: 1"),
            "schema",
            id="wrong-schema",
        ),
        pytest.param(
            _safety_text(
                metadata="schema: physical-agent/safety/v1\nowner: agent\nrevision: 1"
            ),
            "owner",
            id="wrong-owner",
        ),
        pytest.param(
            _safety_text(
                metadata="schema: physical-agent/safety/v1\nowner: human\nrevision: true"
            ),
            "positive integer",
            id="boolean-revision",
        ),
        pytest.param(
            _safety_text(
                rules=(
                    "require_human_approval_for_real_hardware: 'true'\n"
                    "allow_autonomous_execution: true\n"
                    "max_action_timeout_s: 30\n"
                    "forbid_duplicate_action_ids: true"
                )
            ),
            "must be a boolean",
            id="string-boolean",
        ),
        pytest.param(
            _safety_text(
                rules=(
                    "require_human_approval_for_real_hardware: true\n"
                    "allow_autonomous_execution: true\n"
                    "max_action_timeout_s: 0\n"
                    "forbid_duplicate_action_ids: true"
                )
            ),
            "positive finite",
            id="zero-timeout",
        ),
        pytest.param(
            _safety_text(
                rules=(
                    "require_human_approval_for_real_hardware: true\n"
                    "allow_autonomous_execution: true\n"
                    "max_action_timeout_s: 30"
                )
            ),
            "missing required keys",
            id="missing-key",
        ),
        pytest.param(
            _safety_text(
                rules=(
                    "require_human_approval_for_real_hardware: true\n"
                    "allow_autonomous_execution: true\n"
                    "max_action_timeout_s: 30\n"
                    "forbid_duplicate_action_ids: true\n"
                    "ignore_tof: true"
                )
            ),
            "unknown keys",
            id="unknown-key",
        ),
        pytest.param(
            _safety_text(
                rules=(
                    "require_human_approval_for_real_hardware: true\n"
                    "allow_autonomous_execution: true\n"
                    "allow_autonomous_execution: false\n"
                    "max_action_timeout_s: 30\n"
                    "forbid_duplicate_action_ids: true"
                )
            ),
            "duplicate key",
            id="duplicate-key",
        ),
        pytest.param(
            _safety_text(rules="- not\n- a\n- mapping"),
            "must be a mapping",
            id="non-mapping",
        ),
    ],
)
def test_safety_policy_rejects_invalid_contract(tmp_path, text, message):
    sidecars = StateSidecars(tmp_path / "workspace")
    sidecars.safety_path.parent.mkdir(parents=True)
    sidecars.safety_path.write_text(text, encoding="utf-8")

    with pytest.raises(SafetyPolicyError, match=message) as exc_info:
        sidecars.read_safety_snapshot()

    assert exc_info.value.code == SAFETY_POLICY_INVALID


@pytest.mark.parametrize(
    ("key", "first", "second"),
    [
        ("schema", "wrong", "physical-agent/safety/v1"),
        ("owner", "agent", "human"),
        ("revision", "0", "1"),
    ],
)
def test_safety_policy_rejects_duplicate_front_matter_keys(
    tmp_path,
    key,
    first,
    second,
):
    metadata = (
        "schema: physical-agent/safety/v1\n"
        "owner: human\n"
        "revision: 1"
    )
    metadata = metadata.replace(f"{key}: {second}", f"{key}: {first}\n{key}: {second}")
    sidecars = StateSidecars(tmp_path / "workspace")
    sidecars.safety_path.parent.mkdir(parents=True)
    sidecars.safety_path.write_text(_safety_text(metadata=metadata), encoding="utf-8")

    with pytest.raises(SafetyPolicyError, match="duplicate key") as exc_info:
        sidecars.read_safety_snapshot()

    assert exc_info.value.code == SAFETY_POLICY_INVALID


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (
            _safety_text().replace("## Rules", "## Limits", 1),
            "exactly one `## Rules`",
        ),
        (
            _safety_text(
                after_rules=(
                    "\n\n## Rules\n\n```yaml\n"
                    "require_human_approval_for_real_hardware: true\n"
                    "allow_autonomous_execution: true\n"
                    "max_action_timeout_s: 30\n"
                    "forbid_duplicate_action_ids: true\n"
                    "```"
                )
            ),
            "exactly one `## Rules`",
        ),
        (
            _safety_text(
                after_rules=(
                    "\n\n```yaml\n"
                    "require_human_approval_for_real_hardware: true\n"
                    "allow_autonomous_execution: true\n"
                    "max_action_timeout_s: 30\n"
                    "forbid_duplicate_action_ids: true\n"
                    "```"
                )
            ),
            "exactly one in-section YAML",
        ),
    ],
)
def test_safety_policy_rejects_missing_or_ambiguous_rules_sections(
    tmp_path,
    text,
    message,
):
    sidecars = StateSidecars(tmp_path / "workspace")
    sidecars.safety_path.parent.mkdir(parents=True)
    sidecars.safety_path.write_text(text, encoding="utf-8")

    with pytest.raises(SafetyPolicyError, match=message) as exc_info:
        sidecars.read_safety_snapshot()

    assert exc_info.value.code == SAFETY_POLICY_INVALID


def test_safety_rules_yaml_does_not_cross_into_later_section(tmp_path):
    sidecars = StateSidecars(tmp_path / "workspace")
    sidecars.safety_path.parent.mkdir(parents=True)
    sidecars.safety_path.write_text(
        "---\n"
        "schema: physical-agent/safety/v1\n"
        "owner: human\n"
        "revision: 1\n"
        "---\n\n"
        "# Safety Policy\n\n"
        "## Rules\n\nRules are missing here.\n\n"
        "## Agent Guidance\n\n"
        f"{GUIDANCE}\n\n"
        "```yaml\n"
        "require_human_approval_for_real_hardware: true\n"
        "allow_autonomous_execution: true\n"
        "max_action_timeout_s: 30\n"
        "forbid_duplicate_action_ids: true\n"
        "```\n",
        encoding="utf-8",
    )

    with pytest.raises(SafetyPolicyError, match="in-section YAML") as exc_info:
        sidecars.read_safety_snapshot()

    assert exc_info.value.code == SAFETY_POLICY_INVALID


def test_safety_read_missing_file_fails_closed_without_creating_it(tmp_path):
    store = SqliteStateStore(tmp_path / "workspace")

    with pytest.raises(SafetyPolicyError) as exc_info:
        store.read_safety()

    assert exc_info.value.code == SAFETY_POLICY_MISSING
    assert not store.file("safety").exists()


def test_safety_read_invalid_utf8_uses_stable_policy_error(tmp_path):
    store = SqliteStateStore(tmp_path / "workspace")
    store.path.mkdir(parents=True)
    store.file("safety").write_bytes(b"\xff\xfe\x00")

    with pytest.raises(SafetyPolicyError) as exc_info:
        store.read_safety_snapshot()

    assert exc_info.value.code == SAFETY_POLICY_INVALID


def test_malformed_fresh_safety_template_does_not_create_database(tmp_path):
    config_path = write_default_config(
        tmp_path / "physical-agent.yaml",
        overwrite=True,
    )
    (tmp_path / "SAFETY.template.md").write_text(
        "not a safety policy\n",
        encoding="utf-8",
    )
    store = open_state_store(config_path=config_path)

    with pytest.raises(SafetyPolicyError):
        store.initialize()

    assert not store.db_path.exists()


def test_existing_workspace_missing_safety_is_not_repaired_by_initialize(tmp_path):
    _, store = _project(tmp_path)
    store.file("safety").unlink()

    with pytest.raises(SafetyPolicyError) as exc_info:
        store.initialize()

    assert exc_info.value.code == SAFETY_POLICY_MISSING
    assert not store.file("safety").exists()


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


def test_safety_write_and_workspace_reset_preserve_guidance_and_increment_revision(
    tmp_path,
):
    _, store = _project(tmp_path)
    store.file("safety").write_text(_safety_text(), encoding="utf-8")

    store.write_safety({"allow_autonomous_execution": False})
    after_write = store.read_safety_snapshot()

    assert after_write.hard.revision == 2
    assert after_write.hard.rules["allow_autonomous_execution"] is False
    assert after_write.agent_guidance == GUIDANCE

    store.initialize(overwrite=True)
    after_reset = store.read_safety_snapshot()

    assert after_reset.hard.revision == 3
    assert dict(after_reset.hard.rules) == DEFAULT_SAFETY_RULES
    assert after_reset.agent_guidance == GUIDANCE


def test_malformed_safety_blocks_reset_before_database_is_cleared(tmp_path):
    _, store = _project(tmp_path)
    store.append_memory_note("must survive failed reset")
    store.file("safety").write_text("not front matter", encoding="utf-8")

    with pytest.raises(SafetyPolicyError):
        store.initialize(overwrite=True)

    with sqlite3.connect(store.db_path) as conn:
        contents = [
            str(row[0])
            for row in conn.execute(
                "SELECT content FROM memory_notes ORDER BY id"
            ).fetchall()
        ]
    assert contents == ["must survive failed reset"]


def test_safety_write_uses_same_directory_atomic_replace(tmp_path, monkeypatch):
    _, store = _project(tmp_path)
    replacements: list[tuple[Path, Path]] = []
    from physical_agent.state import sidecars as sidecars_module

    original_replace = sidecars_module.os.replace

    def record_replace(source, target):
        replacements.append((Path(source), Path(target)))
        return original_replace(source, target)

    monkeypatch.setattr(sidecars_module.os, "replace", record_replace)

    store.write_safety({"max_action_timeout_s": 7})

    assert len(replacements) == 1
    source, target = replacements[0]
    assert source.parent == target.parent == store.path
    assert target == store.file("safety")
    assert not source.exists()
    assert store.read_safety()["rules"]["max_action_timeout_s"] == 7


def test_safety_atomic_replace_failure_preserves_previous_file(tmp_path, monkeypatch):
    _, store = _project(tmp_path)
    before = store.file("safety").read_bytes()
    from physical_agent.state import sidecars as sidecars_module

    def fail_replace(_source, _target):
        raise OSError("replace blocked")

    monkeypatch.setattr(sidecars_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace blocked"):
        store.write_safety({"max_action_timeout_s": 7})

    assert store.file("safety").read_bytes() == before
    assert list(store.path.glob(".SAFETY.md.*.tmp")) == []


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


def test_doctor_warns_but_keeps_simulation_compatible_without_guidance(tmp_path):
    config_path, _store = _project(tmp_path)

    checks = {check.name: check for check in run_doctor(config_path)}

    guidance = checks["workspace:safety-guidance"]
    assert guidance.ok is True
    assert guidance.message.startswith("WARNING:")
    assert doctor_ok(list(checks.values())) is True


def test_doctor_fails_hardware_workspace_without_guidance(tmp_path):
    config_path, _store = _project(tmp_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["robots"]["arm_1"]["execution_mode"] = "hardware"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    checks = {check.name: check for check in run_doctor(config_path)}

    guidance = checks["workspace:safety-guidance"]
    assert guidance.ok is False
    assert "arm_1" in guidance.message
    assert doctor_ok(list(checks.values())) is False


def test_doctor_accepts_hardware_guidance_within_budget(tmp_path):
    config_path, store = _project(tmp_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["robots"]["arm_1"]["execution_mode"] = "hardware"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    store.file("safety").write_text(_safety_text(), encoding="utf-8")

    checks = {check.name: check for check in run_doctor(config_path)}

    assert checks["workspace:safety-guidance"].ok is True
    assert "within" in checks["workspace:safety-guidance"].message


def test_doctor_rejects_hardware_guidance_over_shared_budget(tmp_path):
    config_path, store = _project(tmp_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["robots"]["arm_1"]["execution_mode"] = "hardware"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    store.file("safety").write_text(
        _safety_text(guidance="x" * 5000),
        encoding="utf-8",
    )

    checks = {check.name: check for check in run_doctor(config_path)}

    assert checks["workspace:safety-guidance"].ok is False
    assert "exceeds" in checks["workspace:safety-guidance"].message


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
