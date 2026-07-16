# R8.1 Stage Review Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the R-stage review findings without unfreezing any new product or runtime capability.

**Architecture:** SQLite remains the runtime and log truth; `LOG.md` becomes an atomically rebuilt, cross-process-serialized, non-control-flow-blocking mirror. Existing claim ownership correlates in-progress Gate evidence without adding a persistent obligation engine. `ChatPlan` keeps the same JSON wire while OpenAPI exposes canonical `AgentOutput` typing.

**Tech Stack:** Python 3.11+, SQLite, Pydantic v2/FastAPI OpenAPI, pytest, React/Vite/Playwright, Ink/TUI, GitHub Actions.

## Global Constraints

- `driver.execute` remains exclusive to the watch execution call stack.
- Every physical action still passes watch-owned SafetyGate against file-truth `SAFETY.md` before execution.
- SQLite Action Board/feedback remain runtime truth; `AgentOutput` remains a compiled/materialized public model.
- Do not introduce VNext-3/4, W4/W5/W6.2, F0/F5/F6, B4-vec, registry/read-model, or automatic replan capability.
- Do not modify or stage the two protected untracked briefs or the three protected architecture snapshots.
- Use test-first RED/GREEN evidence for every production behavior change.

---

### Task 1: Make LOG mirror cross-process safe and non-blocking to control flow

**Files:**
- Modify: `physical_agent/state/sidecars.py`
- Modify: `physical_agent/state/sqlite.py`
- Modify: `physical_agent/watch/runtime.py`
- Test: `tests/test_sidecar_behavior.py`
- Test: `tests/test_watch_timeouts.py`
- Test: `tests/test_api_server.py`

**Interfaces:**
- `SqliteStateStore.append_log(message, actor=None) -> None` continues to commit SQLite first and does not surface mirror-only failures.
- A focused sidecar renderer writes the complete SQLite log snapshot at an exact revision through same-directory temp file + flush/fsync + `os.replace`.
- A second `BEGIN IMMEDIATE` phase serializes snapshot/read/write across processes; every sync reads the latest committed SQLite entries, so a late writer cannot overwrite a newer mirror.

- [ ] Write a spawn-based multiprocessing regression proving all messages and the exact revision survive in both SQLite and `LOG.md`.
- [ ] Run the multiprocessing test and capture RED lost entries/revision mismatch against `33b062b`.
- [ ] Write mirror-failure regressions proving SQLite truth and doctor stale diagnostics remain, while append callers do not fail.
- [ ] Write watch/API RED regressions proving a mirror failure currently skips timeout halt or post-execution verification and can turn a committed API mutation into an error.
- [ ] Implement latest-snapshot mirror rebuild, atomic replace, and mirror-only error containment.
- [ ] Move timeout halt ahead of persistence work so even a non-mirror persistence failure cannot suppress the safety mitigation.
- [ ] Run focused sidecar/watch/API tests GREEN, then run the complete state/backend/watch/safety group.
- [ ] Commit only Task 1 files.

### Task 2: Correlate in-progress Gate evidence with the current claim owner

**Files:**
- Modify: `physical_agent/state/base.py`
- Modify: `physical_agent/state/sqlite.py`
- Modify: `physical_agent/application/output_projection.py`
- Modify: `physical_agent/api/server.py`
- Modify: `physical_agent/mcp/server.py`
- Modify as required: `physical_agent/agent/runtime.py`, `physical_agent/agent/chat_runtime.py`
- Test: `tests/test_state_store.py`
- Test: `tests/test_output_projection.py`
- Test: `tests/test_api_server.py`
- Test: `tests/test_mcp_server.py`

**Interfaces:**
- Add `StateStore.read_action_claim_owners() -> dict[str, str]`, backed by existing `actions.claim_owner`; do not add schema columns or a task/attempt ledger.
- Add optional `claim_owners: Mapping[str, str] | None` to materialization/project functions and pass it from every current-state adapter.
- For `in_progress`, a canonical watch Gate event satisfies the task only when `event.executor_id == claim_owners[action_id]`; mismatched prior-owner evidence is treated as stale, not forged. Pending behavior remains unchanged.

- [ ] Write RED projection tests for successor claim + old owner pass, matching owner pass, and missing owner fail-closed behavior.
- [ ] Write RED state/API/MCP adapter tests proving claim owners reach current projection but are not added as a new public Action payload.
- [ ] Implement the read-only claim-owner query and projection correlation.
- [ ] Update all current projection call sites without adding a second read model.
- [ ] Run focused projection/state/API/MCP tests GREEN and safety AST tests.
- [ ] Commit only Task 2 files.

### Task 3: Publish canonical ChatPlan.agent_output in OpenAPI

**Files:**
- Modify: `physical_agent/protocol/schemas.py`
- Modify as required: `physical_agent/protocol/agent_output.py`, `physical_agent/protocol/__init__.py`
- Test: `tests/test_api_server.py`
- Test: `tests/test_chat_runtime.py`
- Test: `tests/test_output_projection.py`

**Interfaces:**
- The JSON wire stays `plan.agent_output: object|null` with the existing AgentOutput fields.
- Pydantic/FastAPI schema must resolve `ChatPlan.agent_output` to the canonical `AgentOutput` component, not `additionalProperties: true`.
- `ChatPlan.actions` remains absent and old persisted extra fields remain ignored according to the existing compatibility boundary.

- [ ] Write a RED OpenAPI test that resolves `ChatPlan.agent_output` and requires an `AgentOutput` reference/schema.
- [ ] Implement the minimal cycle-safe forward reference or explicit canonical JSON-schema binding.
- [ ] Add/adjust runtime serialization tests only where the typed value changes Python-side behavior.
- [ ] Run API/chat/projection tests GREEN.
- [ ] Commit only Task 3 files.

### Task 4: Close formal docs, evidence, and PR metadata

**Files:**
- Modify: `docs/SPEC.zh-CN.md`
- Modify: `docs/PLAYBOOK.zh-CN.md`
- Modify: `docs/REFACTORING.zh-CN.md`
- Modify: `docs/specs/001-architecture-simplification/spec.md`
- Modify: `docs/specs/001-architecture-simplification/plan.md`
- Modify: `docs/specs/001-architecture-simplification/tasks.md`
- Modify: `tests/test_current_docs.py`
- Delete at final closure: `docs/brief-r8-1-review-hardening.zh-CN.md`
- External: update draft PR #1 title/body without changing draft state.

**Interfaces:**
- R8 historical closure evidence remains intact; R8.1 records review findings and their actual commit/CI evidence.
- Evidence matrix rows identify the correct R3 and R8 commit/run mapping.
- REFACTORING §3 records the R5-browser/R6 ordering deviation and combined R6/R7 rollback granularity without rewriting history.

- [ ] Write RED current-doc assertions for spec header, plan rows, evidence mappings, PLAYBOOK T3 status, deviation record, and R8.1 freeze statement.
- [ ] Update formal docs to the post-review state; keep protected snapshots untouched.
- [ ] Run current-doc/golden/Moce tests GREEN and `git diff --check`.
- [ ] Update PR #1 title/body to describe R0-R8 plus R8.1, retaining draft state.
- [ ] Commit the documentation/test closure after implementation evidence exists.

### Task 5: Full verification, independent review, and branch closure

**Files:**
- Verify only; fixes from review must follow the same TDD and scoped-review rules.

- [ ] Run full Python pytest.
- [ ] Run frontend `tsc -b && vite build` and `CI=1` Playwright.
- [ ] Run TUI typecheck, tests, scenario matrix, and build.
- [ ] Run clean-wheel base/server-extra smoke.
- [ ] Run multiprocessing LOG, timeout-halt, stale-Gate, OpenAPI, safety AST, docs/golden, and residue scans.
- [ ] Dispatch an independent whole-change review; fix all Critical/Important findings and re-review.
- [ ] Remove the round brief, update final evidence, commit, push, and wait for exact-head Push/PR CI success.
- [ ] Confirm protected brief hashes/snapshots, clean index, and zero ahead/behind; do not unfreeze new features.
