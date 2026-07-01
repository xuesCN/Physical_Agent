# Next Session Brief: D3.1 Watch Heartbeat Watchdog Policy

> 目标：在 D3 已接入 `PhysicalDriver.heartbeat()` / `halt()` hook 的基础上，给 `WatchRuntime` 增加 watch 侧软件 watchdog policy：连续 heartbeat 失败计数、阈值触发 best-effort halt、恢复审计。未 push，未开 PR。

## 起始状态

- 分支：`codex/openai-tool-loop-foundation`
- 起始 HEAD：`14c9dcb Add watch heartbeat and halt safety hooks`
- 开始前 tracked worktree 干净：`git status --short --untracked-files=no` 无输出。
- 完整 `git status --short` 仅有未跟踪 `.tmp/` 测试产物；清理时有日志文件被 Windows 进程占用，本轮继续忽略且不提交。

## 本轮范围

- 在 `WatchConfig` 增加小而明确的 watchdog 配置：
  - `heartbeat_failure_threshold`
  - `halt_on_heartbeat_failure`
- 在 `WatchRuntime` 维护每个 robot 的连续 heartbeat 失败次数。
- heartbeat 成功后重置对应 robot 的失败计数，并在曾失败后写恢复审计。
- heartbeat 连续失败达到阈值时，按配置对该 driver best-effort 调 `halt()`。
- 同一轮连续失败只触发一次 watchdog halt；恢复成功后允许下一轮失败重新触发。
- watchdog halt 成功、失败、禁用均写 feedback/log 审计。

## 安全边界

执行链继续保持：

```text
proposal -> watch -> SafetyGate.validate() -> driver.execute() -> driver transport
```

- watchdog policy 只在 watch side 运行。
- `heartbeat()` / `halt()` 仍只由 watch 调用。
- API/GUI/agent 不新增 halt、heartbeat、driver execute 入口。
- 不修改请求侧执行边界。

## 明确不做

- 不做 ServoBus。
- 不做 Feetech/Dynamixel。
- 不接真实硬件。
- 不做独立硬件 E-stop 线。
- 不做固件 deadman。
- 不接 Agents SDK。
- 不接 embeddings/sqlite-vec。

## 验收口径

- 连续 heartbeat 失败会按 robot 计数。
- 未达到阈值时不 halt。
- 达到阈值时 best-effort halt 一次，并写 `driver_watchdog_halt` 审计。
- 连续失败期间不重复 halt 刷屏。
- heartbeat 恢复后重置计数，并写 `driver_heartbeat_recovered` 审计。
- `halt_on_heartbeat_failure=false` 达到阈值也不 halt，但仍审计 threshold reached。
- watchdog halt 抛异常会审计，watch 继续运行。
- `heartbeat_enabled=false` 时 heartbeat/watchdog policy 均不运行。
- agent/API/GUI 仍不能直接 import driver 或调用 driver execute/heartbeat/halt。

