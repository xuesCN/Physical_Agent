# Session Handoff: Hardware Bringup Regression

> 目标：在不做大重构、不接 Agents SDK / RAG / 新 GUI 功能、不发送真实运动指令的前提下，确认当前分支是否保持重构前硬件运行路径，并对 mock / xiaozhi_mcp / moce 相关路径做软件回归与低风险 smoke。未 push，未开 PR。

## 起始状态

- 分支：`codex/openai-tool-loop-foundation`
- 起始 HEAD：`bc12329 Add watch heartbeat watchdog policy`
- 开始前 tracked worktree 干净：`git status --short --untracked-files=no` 无输出。
- 完整 `git status --short` 仅有未跟踪 `.tmp/` 测试产物；本轮继续忽略且不提交。

## 旧硬件连接路径

重构前和当前代码保持同一条硬件执行路径：

```text
agent / gui / chat / api
  -> StateStore pending action
  -> watch
  -> SafetyGate.validate()
  -> driver.execute(action)
  -> hardware / simulator transport
```

关键边界：

- agent / api / gui 只读写 StateStore 或提交 pending action proposal。
- `WatchRuntime` 是唯一加载 driver、连接硬件、调用 `driver.execute()` 的执行侧。
- D3 / D3.1 新增的 `heartbeat()`、`halt()`、watchdog policy 仍只在 watch side 调用。
- API/GUI/agent 没有新增 direct execute / heartbeat / halt 入口。

## 已检查的硬件相关代码和配置

- 文档：
  - `README.zh-CN.md`
  - `HANDOFF.zh-CN.md`
  - `docs/session-handoff-d3.1-watchdog-policy.zh-CN.md`
- runtime / 边界：
  - `physical_agent/watch/runtime.py`
  - `physical_agent/watch/safety.py`
  - `physical_agent/drivers/base.py`
  - `physical_agent/drivers/loader.py`
  - `physical_agent/drivers/registry.py`
  - `physical_agent/doctor.py`
  - `physical_agent/cli.py`
  - `tests/test_safety_boundaries.py`
- driver / transport：
  - `physical_agent/drivers/mock_arm.py`
  - `physical_agent/drivers/mock_rover.py`
  - `physical_agent/drivers/xiaozhi_mcp.py`
  - `physical_agent/drivers/transport/websocket.py`
  - `physical_agent/drivers/transport/serial.py`
  - `physical_agent/drivers/transport/loopback.py`
- examples：
  - `examples/quickstart/physical-agent.yaml`
  - `examples/xiaozhi_mcp_hardware/physical-agent.yaml`
  - `examples/xiaozhi_mcp_hardware/physical_driver.yaml`
  - `examples/moce_arm/physical-agent.yaml`
  - `examples/moce_arm/physical-agent.partial-hardware.yaml`
  - `examples/moce_arm/physical_driver.yaml`
  - `examples/moce_arm/driver.py`

## 边界检查结果

静态扫描：

```powershell
rg -n "physical_agent\.drivers|from physical_agent\.drivers|import physical_agent\.drivers|\.driver\.execute|driver\.execute|\.driver\.heartbeat|driver\.heartbeat|\.driver\.halt|driver\.halt" physical_agent\agent physical_agent\api physical_agent\gui physical_agent\llm -S
```

结果：

- 仅发现既有 allowlist：
  - `physical_agent/agent/onboarding.py` import `physical_agent.drivers.templates`，只复用 inert scaffold 模板。
  - `physical_agent/agent/driver_coder.py` import `physical_agent.drivers.loader`，只在临时候选 driver 的 mock validation 中使用。
  - `physical_agent/agent/driver_coder.py` 调 `loaded.driver.execute()`，只执行 mock observe validation，不属于请求侧执行路径。
- `WatchRuntime` 仍是唯一业务运行时直接调用：
  - `loaded.driver.execute(action)`
  - `loaded.driver.heartbeat()`
  - `loaded.driver.halt()`

## 发现并修复的兼容性问题

实测 `examples/moce_arm/physical-agent.partial-hardware.yaml` 指向已存在的旧 Markdown workspace：

```text
examples/moce_arm/workspace-partial-wrist-gripper/
```

但该旧配置没有显式写：

```yaml
workspace:
  backend: markdown
```

当前新项目默认 backend 已切到 SQLite，因此修复前 `state-check` / `inspect` 会把这个旧 Markdown workspace 误判为未初始化。

最小修复：

- 在 `load_config()` 中增加 legacy Markdown workspace autodetect。
- 仅当配置省略 `workspace.backend`，且目标 workspace 已有完整 Markdown 协议文件时，自动把 backend 视为 `markdown`。
- 显式 `backend: sqlite` 或新项目无 legacy workspace 时，仍保持 SQLite 默认。

新增测试：

- `test_load_config_autodetects_legacy_markdown_workspace_when_backend_omitted`
- `test_load_config_keeps_sqlite_default_without_legacy_markdown_workspace`

## 软件回归命令和结果

聚焦硬件回归矩阵：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_watch_runtime.py tests\test_driver_contract.py tests\test_xiaozhi_mcp_driver.py tests\test_transport_websocket.py tests\test_transport_serial.py tests\test_transport_loopback.py tests\test_safety_boundaries.py
```

结果：

```text
35 passed
```

包含 legacy autodetect 的增量聚焦测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_backend_matrix.py::test_load_config_autodetects_legacy_markdown_workspace_when_backend_omitted tests\test_backend_matrix.py::test_load_config_keeps_sqlite_default_without_legacy_markdown_workspace tests\test_watch_runtime.py tests\test_driver_contract.py tests\test_xiaozhi_mcp_driver.py tests\test_transport_websocket.py tests\test_transport_serial.py tests\test_transport_loopback.py tests\test_safety_boundaries.py
```

结果：

```text
37 passed
```

全量 pytest：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果：

```text
193 passed, 1 warning
```

warning：

- FastAPI / Starlette TestClient 对当前 `httpx` 的 deprecation 提示，非本轮新增。

## 低风险 smoke 命令和结果

### Mock quickstart 完整执行链路

命令：

```powershell
$tempRoot = Join-Path $env:TEMP ('physical-agent-hw-smoke-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempRoot | Out-Null
$config = Join-Path $tempRoot 'physical-agent.yaml'
.\.venv\Scripts\physical-agent.exe setup --config $config --smoke-test
.\.venv\Scripts\physical-agent.exe inspect --config $config
```

结果：

```text
Smoke test passed: executed 2 action(s), red_block location is tray.
Robots:
- arm_1: arm via mock_arm (observe, move_to, pick, place)
Pending actions:
- none
```

结论：mock 路径仍可执行，完整链路仍是 `agent -> StateStore action -> watch -> SafetyGate -> mock driver.execute`。

### Moce mock driver 只读/observe smoke

命令：使用 `examples/moce_arm/physical-agent.yaml` 的旧本地 driver 配置，仅 `mode: mock` 下执行 `connect`、`health`、`observe`、`execute(observe)`。

结果：

```text
robot=momo_1
driver=momoagent_driver
mode=mock
health_ok=True
observation_summary=momo_1 is connected in mock mode.
execute_observe_status=completed
```

结论：moce 本地 driver 旧配置仍可加载，mock observe 能力可执行，不触碰串口。

### Xiaozhi / Moce old config doctor/state-check/inspect

命令组：

```powershell
.\.venv\Scripts\physical-agent.exe doctor --config examples/xiaozhi_mcp_hardware/physical-agent.yaml
.\.venv\Scripts\physical-agent.exe state-check --config examples/xiaozhi_mcp_hardware/physical-agent.yaml
.\.venv\Scripts\physical-agent.exe inspect --config examples/xiaozhi_mcp_hardware/physical-agent.yaml

.\.venv\Scripts\physical-agent.exe doctor --config examples/moce_arm/physical-agent.yaml
.\.venv\Scripts\physical-agent.exe state-check --config examples/moce_arm/physical-agent.yaml
.\.venv\Scripts\physical-agent.exe inspect --config examples/moce_arm/physical-agent.yaml

.\.venv\Scripts\physical-agent.exe doctor --config examples/moce_arm/physical-agent.partial-hardware.yaml
.\.venv\Scripts\physical-agent.exe state-check --config examples/moce_arm/physical-agent.partial-hardware.yaml
.\.venv\Scripts\physical-agent.exe inspect --config examples/moce_arm/physical-agent.partial-hardware.yaml
```

结果摘要：

```text
xiaozhi doctor: driver:xiaozhi_1 OK; workspace missing; exit=1
xiaozhi state-check: Backend sqlite; workspace initialized no; exit=1
xiaozhi inspect: workspace not initialized; exit=1

moce mock doctor: driver:momo_1 OK; workspace missing; exit=1
moce mock state-check: Backend sqlite; workspace initialized no; exit=1
moce mock inspect: workspace not initialized; exit=1

moce partial doctor: OK, all Markdown workspace files parsed, driver:momo_1 OK; exit=0
moce partial state-check: Backend markdown; workspace initialized yes; exit=0
moce partial inspect: momo_1 capabilities visible, no pending actions; exit=0
```

说明：

- xiaozhi 示例目录当前没有初始化 workspace；本轮未运行 setup，也未连接真实 xiaozhi。
- moce mock 示例目录当前没有 `examples/moce_arm/workspace/`；本轮未写入该 example workspace。
- moce partial 示例已有旧 Markdown workspace；修复后可被当前代码自动识别并只读检查。

## 真实硬件状态

- 未连接真实 xiaozhi。
- 未连接真实 moce。
- 未启动会连接真实硬件的 watch。
- 未发送任何真实运动指令。
- 未修改真实硬件配置。

如果下一轮要接真实硬件，建议继续按旧流程：

1. 先确认 `.env`、串口、权限、设备 IP。
2. 先跑 `doctor` / `state-check` / `inspect`。
3. 再启动 `watch`。
4. 先用 `observe` 或设备状态能力。
5. 最后再人工确认后发低风险动作，如 xiaozhi `stop` / moce partial `observe`，不要直接跑大幅运动。

## 验收结论

- 旧 driver 配置仍能加载。
- mock 路径可执行。
- xiaozhi driver / WebSocket transport / example watch setup 的测试仍通过。
- moce partial 旧 Markdown workspace 兼容性已恢复。
- watch 仍是唯一硬件执行侧。
- heartbeat / halt / watchdog 不破坏旧 driver；默认 no-op contract 测试通过。
- Python 全量 pytest 通过。

