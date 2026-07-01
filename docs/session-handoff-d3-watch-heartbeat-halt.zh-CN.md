# Session Handoff: D3 Watch Heartbeat 与 Halt Safety Hooks

> 目标：把已有 `PhysicalDriver.heartbeat()` / `halt()` contract 接入 `WatchRuntime` 的常驻循环与安全收尾路径，形成 watch 侧到 driver 的软件安全地基。未 push，未开 PR。

## 起始状态

- 分支：`codex/openai-tool-loop-foundation`
- 起始 HEAD：`7b1706a Add serial and loopback transports`
- 开始前 tracked worktree 干净：`git status --short --untracked-files=no` 无输出。

## 已完成范围

- 新增 brief：
  - `docs/next-session-d3-watch-heartbeat-halt.zh-CN.md`
- 更新配置：
  - `watch.heartbeat_enabled: true`
  - `watch.halt_on_shutdown: true`
- 更新 watch runtime：
  - `WatchRuntime.step()` 每轮调用已加载 driver 的 `heartbeat()`。
  - `WatchRuntime.run_forever()` 继续通过 `step()` 获得同样 heartbeat 行为。
  - `WatchRuntime.shutdown()` 在 disconnect 前 best-effort 调用已加载 driver 的 `halt()`。
  - heartbeat/halt 失败会写入 feedback history/latest 与 watch log，字段包含：
    - `event`
    - `robot_id`
    - `robot`
    - `error_type`
    - `error_message`
  - halt 失败不会阻止 shutdown 继续执行。
- 扩展测试：
  - heartbeat 在 watch step 中被调用。
  - heartbeat 异常会写入 feedback/log，watch 不静默失败。
  - shutdown 会调用 halt。
  - halt 异常会写入 feedback/log，shutdown 仍完成。
  - 默认 no-op driver contract 仍通过。
  - 请求侧安全边界测试继续覆盖 agent/llm/api/gui 不 import drivers，并新增禁止直接调用 `driver.heartbeat` / `driver.halt` hook。

## 安全边界

执行链继续保持：

```text
proposal -> watch -> SafetyGate.validate() -> driver.execute() -> driver transport
```

- `heartbeat()` 与 `halt()` 只在 watch side 调用。
- API/GUI 没有新增 direct heartbeat/halt/execute endpoint 或按钮。
- agent/API/GUI 仍不得 import `physical_agent.drivers.*` 或直接调用 driver 执行 hook。
- driver execute 失败与 SafetyGate 拒绝仍走原有请求侧边界，不向请求侧暴露 halt。

## 重要说明

- 这是软件侧 watch 到 driver 的 safety foundation。
- 这不等于独立硬件 E-stop。
- 真正的高安全场景仍需要设备侧 fail-safe，例如：
  - 独立硬件 E-stop 线。
  - 固件 deadman/watchdog。
  - 心跳超时即停机的硬件/固件契约。

## 未做

- 未做 ServoBus。
- 未做 Feetech/Dynamixel。
- 未接真实硬件。
- 未新增 API/GUI halt 按钮或 endpoint。
- 未改 agent/API/GUI 请求侧执行边界。
- 未接 Agents SDK。
- 未接 embeddings/sqlite-vec。
- 未实现 D3.1 watchdog policy，例如连续 heartbeat 失败阈值、失败后自动 halt 策略、恢复策略。

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
targeted D3 pytest: 15 passed
full pytest: 184 passed, 1 warning
npm.cmd run build: passed
npm.cmd run test:e2e: 8 passed
git diff --check: passed
```

warning：

- Python warning 仍是 FastAPI / Starlette TestClient 对当前 `httpx` 的 deprecation 提示。
- `git diff --check` 仅输出 Windows CRLF 提示，退出码为 0。

## 下一步建议

- D3.1：watchdog policy，定义 heartbeat 失败计数、严重错误路径 best-effort halt、恢复/退避策略与审计字段。
- D2b：按真实硬件选择 ServoBus 或厂商 SDK 路线，再补 Feetech/Dynamixel 或目标设备协议。
