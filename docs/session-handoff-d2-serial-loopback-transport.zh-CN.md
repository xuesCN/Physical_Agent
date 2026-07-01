# Session Handoff: D2 Serial 与 Loopback Transport 地基

> 目标：在 D1 `Transport` contract 上新增标准库 `LoopbackTransport` 与可选 `SerialTransport(pyserial)`，为未来串口/字节流 driver 与 ServoBus 测试打地基。未 push，未开 PR。

## 起始状态

- 分支：`codex/openai-tool-loop-foundation`
- 起始 HEAD：`55addad Add WebSocket transport for xiaozhi driver`
- 开始前 tracked worktree 干净；`git status --short` 扫描未跟踪 `.tmp/pytest-*` 时会提示权限警告，但 `--untracked-files=no` 无输出。

## 已完成范围

- 新增 brief：
  - `docs/next-session-d2-serial-loopback-transport.zh-CN.md`
- 新增 transport：
  - `physical_agent/drivers/transport/loopback.py`
  - `physical_agent/drivers/transport/serial.py`
- 更新导出：
  - `physical_agent/drivers/transport/__init__.py`
- 更新可选依赖：
  - `pyproject.toml` 增加 `serial = ["pyserial>=3.5"]`
- 新增测试：
  - `tests/test_transport_loopback.py`
  - `tests/test_transport_serial.py`

## LoopbackTransport

- 标准库实现，不依赖 pyserial。
- 用途：tests / local simulation，用于验证字节流读写、timeout 和 closed 状态。
- 支持：
  - `open()` / `close()`
  - `write(data)`
  - `read(timeout_s)`
  - `inject_read_data(data)`
  - `drain_written()`
  - `health()`
- 不作为 agent/API/GUI 入口；只是 watch/driver 侧 transport。

## SerialTransport

- `pyserial>=3.5` 是 optional extra：`pip install -e ".[serial]"`。
- 默认 install/runtime 不强制安装 pyserial。
- 未安装 pyserial 时，实例化会报清晰错误：
  - `Install with pip install -e ".[serial]"`
- 支持配置：
  - `port`
  - `baudrate`
  - `timeout_s`
  - `write_timeout_s`
- 支持：
  - `open()` / `close()`
  - `write(data)`
  - `read(timeout_s)`
  - `health()`
- 测试只用 fake serial object，不连接真实串口。

## 未来配置说明

未来 driver config 可以声明 transport：

```yaml
transport:
  kind: serial
  port: COM3
  baudrate: 115200
```

这只是传输层声明；本轮没有实现 ServoBus、寄存器映射、Feetech/Dynamixel 或任何具体舵机协议。

## 安全边界

- 没有修改 agent/tool_loop/API/GUI 请求侧执行边界。
- API/GUI 没有新增 transport、driver、execute、halt 控制入口。
- `physical_agent.drivers.transport` 继续只在 watch/driver 侧使用。
- 执行路径仍然是：

```text
proposal -> watch -> SafetyGate.validate() -> driver.execute() -> driver transport
```

## 未做

- 未做 ServoBus。
- 未做 Feetech/Dynamixel 协议。
- 未做 E-stop/watchdog 策略大改。
- 未改 agent/API/GUI 请求侧执行边界。
- 未接 Agents SDK。
- 未接 embeddings/sqlite-vec。
- 未连接真实串口或真实硬件。

## 验证结果

已运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_transport_loopback.py
.\.venv\Scripts\python.exe -m pytest -q tests\test_transport_serial.py
.\.venv\Scripts\python.exe -m pytest -q tests\test_transport_loopback.py tests\test_transport_serial.py tests\test_transport_websocket.py tests\test_xiaozhi_mcp_driver.py tests\test_driver_contract.py tests\test_safety_boundaries.py
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm.cmd run build
npm.cmd run test:e2e
cd ..
git diff --check
```

结果：

```text
Loopback transport pytest: 3 passed
Serial transport pytest: 4 passed
targeted D2 pytest: 22 passed
full pytest: 180 passed, 1 warning
npm.cmd run build: passed
npm.cmd run test:e2e: 8 passed
git diff --check: passed
```

warning：

- Python warning 仍是 FastAPI / Starlette TestClient 对当前 `httpx` 的 deprecation 提示。
- `git diff --check` 仅有 Windows CRLF 提示，退出码为 0。

## 下一步建议

- D2b：在这个 byte transport 地基上实现可选 ServoBus 层，先选 Feetech 或 Dynamixel 的最小寄存器读写与 packet framing。
- D3：在常驻 watch loop 场景下设计 watchdog / heartbeat / E-stop 的硬件 fail-safe 策略。
