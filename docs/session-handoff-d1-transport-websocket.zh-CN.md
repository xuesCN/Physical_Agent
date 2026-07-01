# Session Handoff: D1 Transport 抽象与 WebSocketTransport

> 目标：新增 watch/driver 侧 Transport 抽象，实现标准库 `WebSocketTransport`，并重构 `xiaozhi_mcp` 的 `ws` 模式复用共享 transport。未 push，未开 PR。

## 起始状态

- 分支：`codex/openai-tool-loop-foundation`
- 起始 HEAD：`0832c0a Harden React dashboard edge flows`
- 开始前 `git status --short` 无输出，工作区干净。

## 已完成范围

- 新增 brief：
  - `docs/next-session-d1-transport-websocket.zh-CN.md`
- 新增 transport 包：
  - `physical_agent/drivers/transport/base.py`
  - `physical_agent/drivers/transport/websocket.py`
  - `physical_agent/drivers/transport/__init__.py`
- `base.py` 定义：
  - `TransportHealth`
  - `Transport` Protocol
  - `TransportError` / `TransportTimeoutError` / `TransportClosedError` / `TransportProtocolError`
- `WebSocketTransport` 使用标准库实现：
  - 支持 `ws://` / `wss://`
  - 执行 HTTP upgrade 与 `Sec-WebSocket-Accept` 校验
  - client 写入 masked text/binary frame
  - 读取 text/binary frame
  - 处理 close frame、ping/pong
  - timeout、closed peer、invalid accept 等错误有明确异常与 `health()` 状态
- 重构 `physical_agent/drivers/xiaozhi_mcp.py`：
  - `XiaozhiMcpWebSocketClient` 保留为设备侧 JSON-RPC/MCP client
  - 底层握手、socket、frame 逻辑迁移到 `WebSocketTransport`
  - `mode: mock` / `mode: http` / `mode: ws` 配置与外部行为保持兼容
  - HTTP JSON-RPC 路径未改
- 新增 `tests/test_transport_websocket.py`：
  - 本地 loopback fake server 测 handshake、text round trip、binary write、invalid scheme、invalid accept、closed peer、timeout、health
- 更新 xiaozhi 测试：
  - 增加断言：`XiaozhiMcpWebSocketClient` 持有 `WebSocketTransport`
  - 增加断言：xiaozhi WS client 类不再复制 `_send_frame` / `_recv_frame` / `_validate_handshake`
- 更新 xiaozhi example README：
  - 说明 `ws` 模式现在通过 shared `WebSocketTransport`
  - 说明 D1 未实现 `SerialTransport` / `ServoBus` / 硬件 watchdog / E-stop
  - 说明 transport 只在 watch/driver 侧使用，agent/API/GUI 仍 proposal-only

## 安全边界

- 本轮没有修改 agent/tool_loop/API/GUI 请求侧执行边界。
- API/GUI 未新增 transport、driver、execute、halt 控制入口。
- `physical_agent/mcp/server.py` 的认知侧 facade 与 `xiaozhi_mcp.py` 的设备侧 MCP client 仍然分离。
- 执行路径仍是：

```text
proposal -> watch -> SafetyGate.validate() -> driver.execute() -> driver transport
```

- `tests/test_safety_boundaries.py` 继续扫描 `agent` / `llm` / `gui` / `api`，防止请求侧 import `physical_agent.drivers.*` 或调用 `driver.execute`。

## 验证结果

已运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_transport_websocket.py tests\test_xiaozhi_mcp_driver.py tests\test_xiaozhi_mcp_example.py tests\test_xiaozhi_mcp_planner.py tests\test_driver_contract.py tests\test_safety_boundaries.py
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm.cmd run build
npm.cmd run test:e2e
cd ..
git diff --check
```

结果：

```text
targeted D1 pytest: 19 passed
full pytest: 173 passed, 1 warning
npm.cmd run build: passed
npm.cmd run test:e2e: 8 passed
git diff --check: passed
```

warning：

- Python warning 仍是 FastAPI / Starlette TestClient 对当前 `httpx` 的 deprecation 提示。
- `git diff --check` 仅输出 Windows CRLF 提示，退出码为 0。

## 未完成 / 下一步建议

- 未做 D2 `SerialTransport`。
- 未做 ServoBus。
- 未做 D3 硬件 heartbeat / watchdog / E-stop 策略。
- 未接 Agents SDK。
- 未接 OpenAI embeddings 或 sqlite-vec。
- 未连接真实小智设备；所有新增测试均使用本地 fake/loopback。
