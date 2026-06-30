# Session Handoff: C2 FastAPI 常驻 watch 与 SSE 增量事件

> 目标：在 C1 FastAPI proposal-only 后端上增加显式开启的后台 watch loop、`/api/events` SSE 增量事件，以及 SQLite proposal 并发测试；继续保持 HTTP 请求侧不执行硬件。

## 已完成范围

- 新增 brief：
  - `docs/next-session-c2-watch-events.zh-CN.md`
- 新增 API watch/event 服务：
  - `physical_agent/api/watch_service.py`
  - `ApiEventBroker`：线程安全 SSE 事件 broker。
  - `ApiWatchService`：FastAPI lifespan 后台任务，懒加载 `WatchRuntime`。
- 扩展 FastAPI app：
  - `create_app(config_path, *, enable_watch=False, watch_interval_s=None)`
  - 默认 `enable_watch=False`，不启动 watch，不加载 `WatchRuntime`。
  - `enable_watch=True` 时才创建后台 watch service。
  - 新增 `GET /api/events`，使用 `StreamingResponse`。
- 扩展 CLI：
  - `physical-agent api --config physical-agent.yaml --host 127.0.0.1 --port 8766 --watch`
  - 可选调试参数：`--watch-interval-s 0.25`
- 并发修复：
  - `Workspace.append_log()` 增加同进程文件级锁，避免 SQLite backend 并发 proposal 时镜像写 `LOG.md` 互相踩踏。

## 安全边界

- `physical_agent.api.server` 顶层 import 不加载：
  - `physical_agent.watch.runtime`
  - `physical_agent.drivers.loader`
- `physical_agent/api/watch_service.py` 顶层不 import watch runtime 或 drivers。
- `WatchRuntime` 只在 `ApiWatchService._run()` 内部懒加载。
- HTTP endpoint 仍只读状态或写 pending proposal / chat / memory / upload / audit。
- 请求处理器不调用：
  - `WatchRuntime.step()`
  - `WatchRuntime.run_forever()`
  - `SafetyGate`
  - `driver.execute`
- 显式启用同进程 watch 时，唯一执行侧仍是后台任务：

```text
pending proposal -> claim_next_ready_action() -> SafetyGate -> driver.execute -> mark
```

## `/api/events` 格式

SSE 每条消息使用稳定 JSON payload：

```text
event: watch_step
data: {"id":3,"payload":{"executed":1,"state":{...}},"ts":"2026-06-30T00:00:00Z","type":"watch_step"}
```

支持事件类型：

- `hello`
  - `payload.version`
  - `payload.watch_enabled`
- `state`
  - `payload.reason`
  - `payload.state.ok`
  - `payload.state.ready`
  - `payload.state.backend`
  - `payload.state.workspace_path`
  - `payload.state.pending_actions`
  - `payload.state.completed_count`
  - `payload.state.cancelled_count`
  - `payload.state.chat_messages`
  - `payload.state.memory_notes`
  - `payload.state.uploads`
- `watch_step`
  - `payload.executed`
  - `payload.state`
- `error`
  - `payload.phase`
  - `payload.error_type`
  - `payload.message`

默认 `/api/events` 是常驻 SSE。测试/调试可传 `?limit=N`，返回 N 条事件后结束；不影响默认常驻行为。

## 测试覆盖

- `tests/test_api_watch_events.py`
  - 默认 `create_app()` 不启动或加载 `WatchRuntime`。
  - `enable_watch=False` 时 `/api/events` 返回 `hello` / `state`。
  - `enable_watch=True` 时 fake `WatchRuntime` 后台 loop 会 `step()`，并发布 `watch_step` / `error`。
  - HTTP 请求传入 `auto_step` 类字段也不会启动 watch。
  - SQLite backend 并发 proposal 写入不丢 action id。
- `tests/test_api_server.py`
  - CLI `--watch` / `--watch-interval-s` 显式传入 `create_app()`。
- `tests/test_safety_boundaries.py`
  - API 目录仍不 import drivers 或调用 `driver.execute`。
  - 独立进程验证 `import physical_agent.api.server` 不加载 watch runtime / driver loader。

## 验证结果

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,server]"
.\.venv\Scripts\python.exe -m pytest -q tests\test_api_server.py tests\test_safety_boundaries.py
.\.venv\Scripts\python.exe -m pytest -q tests\test_api_watch_events.py
.\.venv\Scripts\python.exe -m pytest -q
```

结果：

```text
tests/test_api_server.py tests/test_safety_boundaries.py: 7 passed, 1 warning
tests/test_api_watch_events.py: 5 passed, 1 warning
full pytest: 161 passed, 1 warning
```

warning 来自当前 FastAPI/Starlette TestClient 对 `httpx` 的 deprecation 提示；TestClient 用例真实运行，没有 skip。

## 未完成 / 下一步建议

1. C3 GUI：接 React / AntD / `@ant-design/x` 前端，消费 `/api/state` 与 `/api/events`；继续保持请求侧 proposal-only。
2. C2.1 multipart upload：把当前本地路径 `POST /api/ingest-file` 扩展为浏览器 multipart upload；上传内容仍作为不可信输入，只进入提案上下文。
3. C2 hardening：如果未来需要多进程 API 并发，可考虑给 Markdown 审计镜像写入增加跨进程文件锁；本轮只保证同进程 API/watch 并发。
4. D 阶段前不要把 heartbeat / halt 暴露给请求侧；硬件安全通路仍应保持 watch -> driver -> hardware 方向。
