# Car Agent Self-Contained Driver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a self-contained, watch-side `car_agent` driver bundle that speaks the Level 0 ESP32 car TCP/NDJSON protocol and exposes fail-closed `observe`, `stop`, and bounded `drive_for` capabilities.

**Architecture:** Keep all device-specific network/protocol logic in `car_agent/driver.py` and load it through the existing local-driver manifest path. One asyncio TCP connection serializes compact newline-delimited JSON requests, correlates responses by `id`, and never retries movement. `drive_for` performs watchdog refreshes inside one SafetyGate-approved `execute()` call and always attempts a final top-level `stop`.

**Tech Stack:** Python 3.11+, asyncio streams, Pydantic protocol models, JSON Schema Draft 2020-12 manifest validation, pytest with a real local asyncio TCP server.

## Global Constraints

- `driver.execute` is called only by the watch execution loop; request/proposal/API/LLM/MCP paths must not load or call this driver.
- Every physical action remains subject to watch `SafetyGate`; `SAFETY.md` remains the file source of truth.
- Do not modify the core driver loader, registry, watch runtime, SafetyGate, or shared transport layer.
- Constructor and `capabilities()` perform no network I/O; all socket I/O uses asyncio and an explicit timeout.
- Level 0 is wheels-up bench-only, unauthenticated, open-loop, has no local obstacle stop, and supports no `turn` or encoder feedback.
- Firmware facts are fixed: protocol `moce-physical-agent/v1`, device `moce-car`, project `car_agent`, port 8080, request line `<2048` bytes, watchdog 800ms, runtime speed clamp ±60.
- Motion is not published unless both `max_abs_speed` and `max_duration_ms` are explicitly configured; maximum accepted configuration values are 60 and 28000ms.
- A movement command with an unknown result is never automatically retried or replayed.
- Existing untracked files, root `physical-agent.yaml`, `my_hardware/`, and `docs/brief-hardware-connectivity-review.zh-CN.md` are user work and must remain untouched.

---

### Task 1: Lock the local bundle and fail-closed configuration contract

**Files:**
- Create: `tests/test_car_agent_driver.py`
- Create: `car_agent/physical_driver.yaml`
- Create: `car_agent/driver.py`

**Interfaces:**
- Consumes: `load_driver(robot_id, driver_ref, config, workspace_path, artifacts_path)`.
- Produces: `CarAgentDriver(context: DriverContext)` and a `physical-agent/driver/v1` manifest.

- [ ] **Step 1: Write failing bundle/config tests**

```python
CAR_DRIVER_DIR = Path("car_agent").resolve()


def test_car_agent_loads_without_motion_limits_and_fails_closed(tmp_path):
    loaded = load_driver(
        robot_id="car_1",
        driver_ref=str(CAR_DRIVER_DIR),
        config={"host": "127.0.0.1"},
        workspace_path=tmp_path / "workspace",
        artifacts_path=tmp_path / "workspace" / "artifacts",
    )
    assert type(loaded.driver).__name__ == "CarAgentDriver"
    assert [cap.name for cap in loaded.driver.capabilities()] == ["observe", "stop"]


@pytest.mark.parametrize(
    "config",
    [
        {"host": "127.0.0.1", "max_abs_speed": 10},
        {"host": "127.0.0.1", "max_duration_ms": 100},
        {"host": "127.0.0.1", "max_abs_speed": 61, "max_duration_ms": 100},
        {"host": "127.0.0.1", "max_abs_speed": 10, "max_duration_ms": 28001},
        {"host": "127.0.0.1", "refresh_interval_ms": 501},
        {"host": "127.0.0.1", "request_timeout_s": 0.61},
    ],
)
def test_car_agent_manifest_rejects_unsafe_config_before_connect(tmp_path, config):
    with pytest.raises(ValueError):
        load_driver(
            robot_id="car_1",
            driver_ref=str(CAR_DRIVER_DIR),
            config=config,
            workspace_path=tmp_path / "workspace",
            artifacts_path=tmp_path / "workspace" / "artifacts",
        )
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `\.venv\Scripts\python.exe -m pytest -q tests/test_car_agent_driver.py --basetemp .tmp/pytest-car-agent-red`

Expected: FAIL because `car_agent/physical_driver.yaml` and `CarAgentDriver` do not exist.

- [ ] **Step 3: Add the minimal manifest and constructor/capability shell**

The manifest must require non-empty `host`, use `dependentRequired` in both directions for the two motion limits, reject additional properties, and bound:

```yaml
max_abs_speed: {type: integer, minimum: 1, maximum: 60}
max_duration_ms: {type: integer, minimum: 1, maximum: 28000}
refresh_interval_ms: {type: integer, minimum: 50, maximum: 500, default: 250}
request_timeout_s: {type: number, exclusiveMinimum: 0, maximum: 0.6, default: 0.5}
```

The initial class returns `observe` and `stop`; it stores but does not use host/port/timeouts during construction.

- [ ] **Step 4: Run Task 1 tests and verify GREEN**

Run: `\.venv\Scripts\python.exe -m pytest -q tests/test_car_agent_driver.py --basetemp .tmp/pytest-car-agent-task1`

Expected: all Task 1 tests pass.

- [ ] **Step 5: Commit Task 1**

```powershell
git add -- car_agent/physical_driver.yaml car_agent/driver.py tests/test_car_agent_driver.py
git commit -m "feat: scaffold fail-closed car agent driver"
```

### Task 2: Implement protocol framing, identity handshake, health, observe, and stop

**Files:**
- Modify: `tests/test_car_agent_driver.py`
- Modify: `car_agent/driver.py`

**Interfaces:**
- Produces: `_request(method: str, params: dict | None) -> dict`, `connect`, `disconnect`, `health`, `heartbeat`, `halt`, `observe`, and `execute` handling `observe`/`stop`.
- Protocol errors expose stable local exception types and remote `error.code`; they never depend on remote `error.message`.

- [ ] **Step 1: Add a real asyncio scripted server and failing lifecycle tests**

The fake server binds `127.0.0.1:0`, reads with `await reader.readline()`, records parsed requests, and emits compact JSON plus `\n`. Tests must prove:

```python
async def scenario():
    async with ScriptedCarServer() as server:
        driver = make_driver(
            tmp_path,
            host=server.host,
            port=server.port,
        )
        await driver.connect()
        health = await driver.health()
        observation = await driver.observe()
        stop_result = await driver.execute(action("stop"))
        await driver.disconnect()
        return server, driver, health, observation, stop_result


assert server.methods[:3] == ["health", "capabilities", "stop"]
assert health.ok is True
assert observation.robots["car_1"]["status"] == "moving"
assert observation.robots["car_1"]["moving"] is True
assert observation.robots["car_1"]["tof_valid"] is False
assert stop_result.status == "completed"
assert server.peer_eof_count == 1
```

Add separate RED cases for wrong protocol/device/project, split response chunks, an extra unmatched `id:null` response before the matching response, remote errors where the internal `message` must not appear in the local exception, response timeout, and event-loop responsiveness while the server delays a response.

- [ ] **Step 2: Run the focused lifecycle tests and verify RED**

Run: `\.venv\Scripts\python.exe -m pytest -q tests/test_car_agent_driver.py -k "protocol or lifecycle or observe or timeout or event_loop" --basetemp .tmp/pytest-car-agent-task2-red`

Expected: FAIL because network methods are not implemented.

- [ ] **Step 3: Implement the minimal async NDJSON client**

Use `asyncio.open_connection(self.host, self.port, limit=4096)`, one `asyncio.Lock`, monotonically increasing integer ids, compact `json.dumps(envelope, separators=(",", ":"))`, and `asyncio.timeout(request_timeout_s)`. Reject outgoing payload length `>=2048`; read until a response with the current id arrives; ignore extra responses with other ids; reject malformed/envelope-invalid responses. On EOF, clear the local connection and raise. Do not reconnect or replay.

`connect()` opens once, then calls `health`, `capabilities`, and top-level `stop`; it verifies protocol/device/project and closes on any handshake failure. `disconnect()` only closes the writer and is idempotent. `heartbeat()` raises when health is not OK. `observe()` derives `status` from `moving`, preserves TOF validity fields, and places the full device result in `raw`.

- [ ] **Step 4: Run Task 2 tests and verify GREEN**

Run: `\.venv\Scripts\python.exe -m pytest -q tests/test_car_agent_driver.py --basetemp .tmp/pytest-car-agent-task2`

Expected: Task 1 and Task 2 tests pass.

- [ ] **Step 5: Commit Task 2**

```powershell
git add -- car_agent/driver.py tests/test_car_agent_driver.py
git commit -m "feat: add car agent ndjson lifecycle"
```

### Task 3: Add bounded drive_for refresh and unconditional stop cleanup

**Files:**
- Modify: `tests/test_car_agent_driver.py`
- Modify: `car_agent/driver.py`

**Interfaces:**
- Produces: runtime `drive_for` capability only when local limits exist and remote `drive` was discovered.
- `execute(Action(capability="drive_for", params={"speed": int, "duration_ms": int}))` returns completed only when every drive response reports the requested effective speed, `clamped=false`, `motor_available=true`, and final stop succeeds.

- [ ] **Step 1: Write failing motion capability and execution tests**

Assert the published contract exactly:

```python
drive = next(cap for cap in driver.capabilities() if cap.name == "drive_for")
assert drive.requires_approval is True
assert drive.params_schema["required"] == ["speed", "duration_ms"]
assert drive.params_schema["properties"]["speed"]["minimum"] == -12
assert drive.params_schema["properties"]["speed"]["maximum"] == 12
assert drive.params_schema["properties"]["duration_ms"]["maximum"] == 180
assert drive.constraints["bounds"] == {
    "speed": [-12, 12],
    "duration_ms": [1, 180],
}
assert drive.timeout_s == 3
```

Use the server's `time.monotonic()` arrival timestamps to prove a 180ms action with 50ms refresh produces multiple `execute/drive` frames, every adjacent gap is below 0.8s, and the last motion-related method is `stop`. Add parameterized failures for `clamped:true`, wrong returned speed, `motor_available:false`, remote error, and response timeout; each must end with a stop attempt. Cancel a running task after the first drive and assert `CancelledError` propagates after `stop` is observed.

- [ ] **Step 2: Run the motion tests and verify RED**

Run: `\.venv\Scripts\python.exe -m pytest -q tests/test_car_agent_driver.py -k "drive or cancel or clamp or motor" --basetemp .tmp/pytest-car-agent-task3-red`

Expected: FAIL because `drive_for` is not published or implemented.

- [ ] **Step 3: Implement drive_for minimally**

Publish `drive_for` only after both local limits are valid and the connected remote capability names include `drive`. Derive `timeout_s` as `ceil(max_duration_ms / 1000) + 2`. Defensively reject booleans, non-integers, zero speed, and values outside the same local envelope even though SafetyGate normally rejects them first.

Inside one `execute()` call, send the first drive immediately. Schedule each next send from the previous send-start time, so slow responses do not add `response latency + refresh interval`; both configured request timeout (≤0.6s) and refresh interval (≤0.5s) remain below the 0.8s firmware watchdog. Do not retry a failed drive. Capture normal errors and cancellation separately, attempt a bounded top-level stop in all paths, return failed when cleanup fails, and re-raise cancellation after cleanup.

- [ ] **Step 4: Run Task 3 tests and verify GREEN**

Run: `\.venv\Scripts\python.exe -m pytest -q tests/test_car_agent_driver.py --basetemp .tmp/pytest-car-agent-task3`

Expected: all driver tests pass.

- [ ] **Step 5: Commit Task 3**

```powershell
git add -- car_agent/driver.py tests/test_car_agent_driver.py
git commit -m "feat: add bounded car drive action"
```

### Task 4: Add runnable bundle documentation and Watch/SafetyGate integration coverage

**Files:**
- Create: `car_agent/physical-agent.yaml`
- Create: `car_agent/README.md`
- Create: `car_agent/README.zh-CN.md`
- Create: `tests/test_car_agent_example.py`
- Modify: `docs/hardware-bringup-checklist.zh-CN.md`

**Interfaces:**
- The sample config uses `driver: .`, `execution_mode: hardware`, a replaceable DHCP host, and omits motion limits so a checkout publishes only `observe`/`stop` until the operator adds measured values.
- Watch publishes runtime capabilities; SafetyGate rejects out-of-envelope `drive_for` before any remote drive frame.

- [ ] **Step 1: Write failing example and thin Watch integration tests**

```python
def test_car_agent_bundle_files_exist():
    base = Path("car_agent")
    for name in (
        "driver.py",
        "physical_driver.yaml",
        "physical-agent.yaml",
        "README.md",
        "README.zh-CN.md",
    ):
        assert (base / name).exists()


def test_car_agent_sample_is_explicit_hardware_and_motion_disabled():
    data = yaml.safe_load(Path("car_agent/physical-agent.yaml").read_text(encoding="utf-8"))
    robot = data["robots"]["car_1"]
    assert robot["driver"] == "."
    assert robot["execution_mode"] == "hardware"
    assert robot["config"]["host"] == "REPLACE_WITH_CAR_IP"
    assert "max_abs_speed" not in robot["config"]
    assert "max_duration_ms" not in robot["config"]
```

The Watch test starts the scripted server, builds an isolated temporary config with the same local bundle and safety envelope, points host/port at the server, initializes a SQLite workspace, submits an out-of-bounds drive action, and asserts cancelled state + SafetyGate feedback + zero calls to `driver.execute` and zero remote drive frames.

- [ ] **Step 2: Run example/integration tests and verify RED**

Run: `\.venv\Scripts\python.exe -m pytest -q tests/test_car_agent_example.py --basetemp .tmp/pytest-car-agent-task4-red`

Expected: FAIL because config, READMEs, checklist section, and Watch integration fixture are absent.

- [ ] **Step 3: Add the example config and docs**

Document the first-run order `init → state-check → doctor → inspect/watch`, manual `SAFETY.md` review, IP replacement, trusted 2.4GHz LAN, single-client limitation, no authentication/TLS, mutually exclusive embedded-vs-standalone Watch layouts, local LLM settings, Level 0 wheels-up-only restriction, physical power cut, invalid TOF handling, no turn/encoder/local avoidance, and the fact that Chat only proposes while Watch owns execution. Show how to add both measured motion limits to a local copy after bench calibration; the committed sample must leave them absent and motion disabled. State explicitly that scripted TCP tests are not physical connection or motion acceptance.

- [ ] **Step 4: Run example, safety-boundary, and all car tests**

Run: `\.venv\Scripts\python.exe -m pytest -q tests/test_car_agent_driver.py tests/test_car_agent_example.py tests/test_safety_boundaries.py --basetemp .tmp/pytest-car-agent-task4`

Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 4**

```powershell
git add -- car_agent/physical-agent.yaml car_agent/README.md car_agent/README.zh-CN.md tests/test_car_agent_example.py docs/hardware-bringup-checklist.zh-CN.md
git commit -m "docs: add car agent bring-up bundle"
```

### Task 5: Close living docs, review, and verify the full repository

**Files:**
- Modify: `docs/SPEC.zh-CN.md`
- Modify: `docs/REFACTORING.zh-CN.md`
- Keep: `docs/PLAYBOOK.zh-CN.md`
- Delete: `docs/brief-f5-0-car-agent-driver.zh-CN.md`
- Keep: `docs/superpowers/plans/2026-08-04-car-agent-driver.md`

**Interfaces:**
- SPEC §4 becomes complete only after fresh full-suite evidence exists.
- REFACTORING §1 gets one F5.0 row; §2 gets the implementation summary; §3 records local bundle over builtin/core transport and fail-closed motion-envelope decisions.

- [ ] **Step 1: Run focused mutation-minded verification**

Run: `\.venv\Scripts\python.exe -m pytest -q tests/test_car_agent_driver.py tests/test_car_agent_example.py tests/test_driver_loader.py tests/test_driver_manifest.py tests/test_safety.py tests/test_safety_boundaries.py tests/test_watch_runtime.py tests/test_watch_timeouts.py --basetemp .tmp/pytest-car-agent-focused`

Expected: all selected tests pass; realistic mutations to id matching, envelope publication, response checks, cadence, final stop, and Gate constraints are covered by at least one test.

- [ ] **Step 2: Run the full suite and formatting checks**

```powershell
& .\.venv\Scripts\python.exe -m pytest -q --basetemp .tmp\pytest-car-agent-full
git diff --check
```

Expected: full pytest exit 0 and `git diff --check` produces no output.

- [ ] **Step 3: Request independent code review and fix Critical/Important findings**

The reviewer receives the plan, the scoped diff, the embedded protocol facts, and the two safety constitutions. Re-run covering tests after every fix and perform one scoped re-review.

- [ ] **Step 4: Update living docs and remove the round brief**

Set SPEC F5.0 to completed with exact test counts, add REFACTORING entries, retain the PLAYBOOK implementation guidance, and delete only `docs/brief-f5-0-car-agent-driver.zh-CN.md`.

- [ ] **Step 5: Re-run final evidence after documentation closure**

```powershell
& .\.venv\Scripts\python.exe -m pytest -q --basetemp .tmp\pytest-car-agent-final
git diff --check
```

Expected: full pytest exit 0 after all code and docs edits; diff check clean.

- [ ] **Step 6: Commit and push only scoped files**

```powershell
git add -- car_agent tests/test_car_agent_driver.py tests/test_car_agent_example.py docs/SPEC.zh-CN.md docs/PLAYBOOK.zh-CN.md docs/REFACTORING.zh-CN.md docs/hardware-bringup-checklist.zh-CN.md docs/superpowers/plans/2026-08-04-car-agent-driver.md
git commit -m "feat: add self-contained car agent hardware driver"
git push
```

Do not use `git add -A`; untracked user files are outside this plan.
