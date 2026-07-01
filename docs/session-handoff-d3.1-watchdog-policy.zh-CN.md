# Session Handoff: D3.1 Watch Heartbeat Watchdog Policy

> 目标：在 D3 已接入 `PhysicalDriver.heartbeat()` / `halt()` hook 的基础上，实现 watch 侧软件 watchdog policy：连续 heartbeat 失败计数、阈值触发 best-effort halt、恢复审计。未 push，未开 PR。

## 起始状态

- 分支：`codex/openai-tool-loop-foundation`
- 起始 HEAD：`14c9dcb Add watch heartbeat and halt safety hooks`
- 开始前 tracked worktree 干净：`git status --short --untracked-files=no` 无输出。
- 完整 `git status --short` 仅有未跟踪 `.tmp/` 测试产物；清理时 `.tmp/api-8766.err.log` 被 Windows 进程占用，本轮继续忽略且不提交。

## 已完成范围

- 新增 brief：
  - `docs/next-session-d3.1-watchdog-policy.zh-CN.md`
- 新增 handoff：
  - `docs/session-handoff-d3.1-watchdog-policy.zh-CN.md`
- 更新配置：
  - `watch.heartbeat_failure_threshold: 3`
  - `watch.halt_on_heartbeat_failure: true`
  - `heartbeat_failure_threshold` 使用 Pydantic `ge=1` 校验；关闭阈值 halt 使用 `halt_on_heartbeat_failure: false` 或关闭 `heartbeat_enabled`。
- 更新 watch runtime：
  - `WatchRuntime` 维护每个 robot 的连续 heartbeat 失败次数。
  - heartbeat 成功后重置该 robot 的失败计数。
  - 如果 heartbeat 曾失败，恢复时写 `driver_heartbeat_recovered` feedback/log。
  - heartbeat 失败继续保留 D3 的 `driver_heartbeat` 审计字段：`robot_id`、`robot`、`error_type`、`error_message`。
  - 连续失败达到 `heartbeat_failure_threshold` 后写 `driver_watchdog_halt` feedback/log。
  - `halt_on_heartbeat_failure=true` 时对该 driver best-effort 调 `halt()`。
  - watchdog halt 成功、禁用或抛异常都会审计 `failure_count`、`threshold`、`halt_status`、heartbeat/halt 错误信息。
  - 同一轮连续失败期间只触发一次 watchdog halt；heartbeat 恢复后重置触发标记。
  - watchdog halt 抛异常不会让 watch 崩掉。
- 扩展测试：
  - 连续 heartbeat 失败计数递增。
  - 未达到阈值时不调用 halt。
  - 达到阈值时调用 halt 一次并写 `driver_watchdog_halt`。
  - 连续失败期间不重复 halt。
  - heartbeat 成功后重置计数，并写 `driver_heartbeat_recovered`。
  - `halt_on_heartbeat_failure=false` 时达到阈值不 halt，但仍审计 threshold reached。
  - watchdog halt 抛异常时写 feedback/log，watch 仍继续。
  - `heartbeat_enabled=false` 时不调用 heartbeat/watchdog。
  - `heartbeat_failure_threshold <= 0` 被配置校验拒绝。

## 安全边界

执行链继续保持：

```text
proposal -> watch -> SafetyGate.validate() -> driver.execute() -> driver transport
```

- watchdog policy 只在 watch side 运行。
- `heartbeat()` / `halt()` 仍只由 watch 调用。
- API/GUI 没有新增 halt、heartbeat、driver execute endpoint 或按钮。
- agent/API/GUI 仍不得 import `physical_agent.drivers.*` 或直接调用 driver hook。
- 请求侧安全边界测试继续覆盖 `driver.execute`、`driver.heartbeat`、`driver.halt` 禁止项。

## 重要说明

- 这是 watch-side software watchdog policy。
- 这不是独立硬件 E-stop。
- 这不是固件 deadman/watchdog。
- 如果 watch 进程本身崩溃，只有真实硬件/固件 fail-safe 才能提供最终停机保证。

## 未做

- 未做 ServoBus。
- 未做 Feetech/Dynamixel。
- 未接真实硬件。
- 未做真实硬件 E-stop 线。
- 未改 agent/API/GUI 请求侧执行边界。
- 未新增 API/GUI halt 入口。
- 未接 Agents SDK。
- 未接 embeddings/sqlite-vec。

## 验证结果

已运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_watch_runtime.py tests\test_driver_contract.py tests\test_safety.py tests\test_safety_boundaries.py
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm.cmd run build
npm.cmd run test:e2e
cd ..
git diff --check
```

结果：

```text
targeted D3.1 pytest: 22 passed
full pytest: 191 passed, 1 warning
npm.cmd run build: passed
npm.cmd run test:e2e: 8 passed
git diff --check: passed
```

warning：

- Python warning 仍是 FastAPI / Starlette TestClient 对当前 `httpx` 的 deprecation 提示。
- `git diff --check` 如有 Windows CRLF 提示，退出码仍为 0。

## 下一步建议

- 总体验收/接手文档：把 A/B/C/D 已落地范围、边界和剩余路线统一成一份当前仓库状态说明。
- 或进入 D2b ServoBus：基于 Loopback/SerialTransport 选真实硬件路线，再做 Feetech/Dynamixel 或目标设备协议。

