# Next Session Brief: D2 Serial 与 Loopback Transport 地基

> 目标：在 D1 `Transport` contract 之上新增可测的字节流地基：标准库 `LoopbackTransport` 与可选依赖 `SerialTransport`。本轮不 push，不开 PR。

## 范围

- 新增 `physical_agent/drivers/transport/loopback.py`：
  - 标准库实现，不依赖 pyserial。
  - 支持 `open()` / `close()` / `write(data)` / `read(timeout_s)` / `health()`。
  - 提供测试辅助 `inject_read_data(data)` 与 `drain_written()`，用于本地仿真字节流读写、timeout 与 closed 状态。
- 新增 `physical_agent/drivers/transport/serial.py`：
  - `pyserial>=3.5` 作为可选依赖，放入 `[project.optional-dependencies].serial`。
  - 未安装 pyserial 时给清晰错误：`Install with pip install -e ".[serial]"`。
  - 支持 `port`、`baudrate`、`timeout_s`、`write_timeout_s` 配置。
  - 支持 `open()` / `close()` / `write(data)` / `read(timeout_s)` / `health()`。
  - 测试只使用 fake serial object，不连接真实串口。
- 更新 `physical_agent/drivers/transport/__init__.py`，保持 D1 `Transport` contract 与 `WebSocketTransport` 行为不破坏。
- 新增测试：
  - `tests/test_transport_loopback.py`
  - `tests/test_transport_serial.py`
- 新增本轮 handoff：
  - `docs/session-handoff-d2-serial-loopback-transport.zh-CN.md`

## 不做

- 不做 ServoBus。
- 不做 Feetech / Dynamixel / 任意具体舵机协议。
- 不做 E-stop / watchdog 策略大改。
- 不改 agent / API / GUI 请求侧执行边界。
- 不接 Agents SDK。
- 不接 embeddings / sqlite-vec。
- 不连接真实串口或真实硬件。

## 安全边界

执行链继续保持：

```text
proposal -> watch -> SafetyGate.validate() -> driver.execute() -> driver transport
```

- `physical_agent.drivers.transport` 只允许 watch/driver 侧使用。
- agent / llm / api / gui 不得 import `physical_agent.drivers.transport` 或其它 driver 执行模块。
- API/GUI 不新增 transport、driver、execute、halt 控制入口。
- 新增 transport 只是 driver 侧字节流能力，不是请求侧执行入口。

## 配置说明草案

未来 driver config 可以声明串口 transport，例如：

```yaml
transport:
  kind: serial
  port: COM3
  baudrate: 115200
```

这只是传输层声明；具体设备语义、寄存器、帧协议与舵机总线不在本轮实现。

## 验证命令

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_transport_loopback.py tests\test_transport_serial.py tests\test_transport_websocket.py tests\test_xiaozhi_mcp_driver.py tests\test_driver_contract.py tests\test_safety_boundaries.py
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm.cmd run build
npm.cmd run test:e2e
cd ..
git diff --check
```

## 交付

- `LoopbackTransport` 独立可测。
- `SerialTransport` optional，不安装 pyserial 不影响默认 install/runtime。
- 缺 pyserial 时错误清楚。
- fake serial 测试覆盖 open/write/read/close/health 与 timeout 转换。
- WebSocket/xiaozhi 既有行为不破坏。
- 请求侧安全边界不变。
- Python 全量 pytest 与前端 build/e2e 通过。
- 本地 commit：`Add serial and loopback transports`。
