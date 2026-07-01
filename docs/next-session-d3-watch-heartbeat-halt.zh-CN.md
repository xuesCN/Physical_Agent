# Next Session Brief: D3 Watch Heartbeat 与 Halt Safety Hooks

> 目标：把已有 `PhysicalDriver.heartbeat()` / `halt()` contract 接入 `WatchRuntime` 的常驻循环与安全收尾路径，形成 watch 侧到 driver 的软件安全地基。本轮不 push，不开 PR。

## 范围

- `WatchRuntime` 在每个 watch step 周期对已加载 driver 调用 `driver.heartbeat()`。
  - 默认 no-op driver 不受影响。
  - `run_forever()` 继续通过 `step()` 获得同样行为。
  - heartbeat 失败时写入 feedback/log，包含 `robot_id`、错误类型、错误消息。
- `WatchRuntime.shutdown()` 在 disconnect 前 best-effort 调用所有已加载 driver 的 `halt()`。
  - halt 失败时写入 feedback/log。
  - shutdown 继续完成，不让 halt 失败掩盖后续 driver 收尾。
- 如需新增配置，只增加小开关：
  - `watch.heartbeat_enabled: true`
  - `watch.halt_on_shutdown: true`
- 新增或扩展 watch runtime 测试，覆盖 heartbeat/halt 的成功、异常与审计记录。
- 新增本轮 handoff：
  - `docs/session-handoff-d3-watch-heartbeat-halt.zh-CN.md`

## 不做

- 不做 ServoBus。
- 不做 Feetech / Dynamixel / 任意具体舵机协议。
- 不连接真实硬件。
- 不新增 API/GUI 的 direct halt、heartbeat、driver execute 入口。
- 不改 agent/API/GUI 请求侧执行边界。
- 不接 Agents SDK。
- 不接 embeddings / sqlite-vec。

## 安全边界

执行链继续保持：

```text
proposal -> watch -> SafetyGate.validate() -> driver.execute() -> driver transport
```

- `heartbeat()` 与 `halt()` 都只在 watch side 调用。
- API/GUI 不提供直接硬件 halt 入口；agent 也不获得 heartbeat/halt 工具。
- 这是软件侧 watch 到 driver 的 safety foundation，不等于独立硬件 E-stop。
- 真正的高安全场景仍需要独立硬件 E-stop 线、固件 deadman/watchdog 与设备侧 fail-safe。

## 配置说明

默认配置保持兼容：

```yaml
watch:
  tick_ms: 500
  require_human_approval: false
  heartbeat_enabled: true
  halt_on_shutdown: true
```

如果未来某个测试或设备不需要 watch 心跳，可以关闭 `heartbeat_enabled`；如果某个 driver 的收尾策略不适合 halt，可以关闭 `halt_on_shutdown`。本轮不强制任何真实硬件 driver 实现这两个 hook。

## 验证命令

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_watch_runtime.py tests\test_driver_contract.py tests\test_safety.py tests\test_safety_boundaries.py
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm.cmd run build
npm.cmd run test:e2e
cd ..
git diff --check
```

## 交付

- watch side 会周期性 heartbeat。
- shutdown 会 best-effort halt。
- heartbeat/halt 异常可审计。
- 默认 no-op driver contract 仍通过。
- 请求侧安全边界不变。
- Python 全量 pytest 与前端 build/e2e 通过。
- 本地 commit：`Add watch heartbeat and halt safety hooks`。

## 下一步建议

- D3.1：watchdog policy，定义 heartbeat 失败阈值、连续失败处置、严重错误路径 best-effort halt 与恢复策略。
- D2b：按真实硬件选择 ServoBus 或厂商 SDK 路线，再补具体协议与固件 deadman 契约。
