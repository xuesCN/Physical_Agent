# Next Session Brief: C2 FastAPI 常驻 watch 与 SSE 增量事件

## 目标

在 C1 FastAPI proposal-only 后端基础上，增加显式开启的后台 watch loop 和 `/api/events` SSE 增量事件，同时继续守住执行边界：

```text
HTTP 请求侧 -> 只读 state 或写 pending proposal
后台 watch -> claim_next_ready_action() -> SafetyGate -> driver.execute -> mark
```

## 范围

- `create_app(config_path, *, enable_watch=False, watch_interval_s=None)` 默认不启动 watch。
- `physical-agent api --config physical-agent.yaml --host 127.0.0.1 --port 8766 --watch` 才启动后台 watch。
- 新增薄的 API watch service，懒加载 `WatchRuntime`。
- 新增 `/api/events`，使用 `StreamingResponse` 输出 SSE。
- endpoint 写入 proposal / task / chat / upload / audit 后发布轻量 `state` 通知。
- 新增并发 proposal 写入测试与 API/watch 懒加载边界测试。

## 不做

- 不做 React / AntD GUI。
- 不做 Agents SDK。
- 不做 OpenAI embeddings 或 sqlite-vec。
- 不做 D1/D2 传输层。
- 不删除 Markdown backend。

## 验收

- 默认 API 行为不启动 `WatchRuntime`。
- 显式 `--watch` / `enable_watch=True` 后后台 watch loop 可运行。
- `/api/events` 在未启用 watch 时仍可返回 `hello` 和 `state`。
- 请求 handler 不调用 watch step、SafetyGate 或 driver execution。
- API 顶层 import 不加载 `physical_agent.watch.runtime` 或 `physical_agent.drivers.loader`。
- SQLite backend 小规模并发 proposal 写入不丢 action id。
- 目标测试与全量 pytest 通过。
