# Next Session Brief: D1 Transport 抽象与 WebSocketTransport

> 目标：在 drivers/watch 内聚层新增轻量 Transport 抽象，并把 `xiaozhi_mcp` 的 WebSocket 底层连接、握手、frame 读写重构为复用共享 `WebSocketTransport`。不 push，不开 PR。

## 范围

- 新增 `physical_agent/drivers/transport/`：
  - `base.py` 定义 `TransportHealth` 与轻量 `Transport` contract。
  - `websocket.py` 实现标准库 `ws://` / `wss://` WebSocketTransport。
  - `__init__.py` 只导出 D1 所需类型。
- `WebSocketTransport` 负责：
  - HTTP upgrade 与 `Sec-WebSocket-Accept` 校验。
  - client masked text/binary frame 写入。
  - text/binary frame 读取、close frame、ping/pong 基础行为。
  - timeout 与清晰错误。
- 重构 `physical_agent/drivers/xiaozhi_mcp.py`：
  - 保持 `mode: mock` / `mode: http` / `mode: ws` 配置行为兼容。
  - `XiaozhiMcpWebSocketClient` 继续作为设备侧 JSON-RPC/MCP client，但底层复用 `WebSocketTransport`。
  - HTTP JSON-RPC 与 mock 行为不变。
- 新增 `tests/test_transport_websocket.py`，使用本地 loopback/fake server，不依赖真实硬件。
- 更新 xiaozhi 相关测试，断言 ws client 底层使用 `WebSocketTransport`。
- 更新 xiaozhi example README 片段，说明 `ws` 模式现在走 shared transport。
- 完成本轮 handoff：`docs/session-handoff-d1-transport-websocket.zh-CN.md`。

## 不做

- 不做 `SerialTransport`、TCP/BLE/CAN transport、ServoBus。
- 不做 E-stop / heartbeat / watchdog 策略大改。
- 不改 agent/tool_loop/API/GUI 请求侧执行边界。
- 不接 Agents SDK。
- 不接 OpenAI embeddings 或 sqlite-vec。
- 不连接真实小智设备；测试只用本地 fake/loopback。

## 安全边界

执行链继续保持：

```text
proposal -> watch -> SafetyGate.validate() -> driver.execute() -> driver transport
```

- `physical_agent.drivers.transport` 只能由 drivers/watch 侧使用。
- agent / llm / api / gui 不得 import `physical_agent.drivers.transport` 或其它 driver 执行模块。
- API/GUI 不新增 transport、driver、execute、halt 控制入口。
- `physical_agent/mcp/server.py` 的认知侧 facade 与 `xiaozhi_mcp.py` 的设备侧 MCP client 继续分离。

## 验证命令

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_transport_websocket.py tests\test_xiaozhi_mcp_driver.py tests\test_xiaozhi_mcp_example.py tests\test_xiaozhi_mcp_planner.py tests\test_driver_contract.py tests\test_safety_boundaries.py
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm.cmd run build
npm.cmd run test:e2e
cd ..
git diff --check
```

## 交付

- `WebSocketTransport` 独立可测。
- xiaozhi `ws` 模式复用 `WebSocketTransport`。
- mock/http/ws 既有行为不破坏。
- 请求侧安全边界测试保持通过。
- Python 全量 pytest 与前端 build/e2e 通过。
- 本地 commit：`Add WebSocket transport for xiaozhi driver`。
