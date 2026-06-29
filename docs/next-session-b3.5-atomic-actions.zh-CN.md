# Next Session Brief：B3.5 / B4a SQLite Atomic Action API

## 背景

B1 / B2 / B3 已完成：核心 runtime 已通过 `StateStore` 抽象访问状态；SQLite backend 仍为 opt-in；`export-audit` / `export_human_view()` 已可为 Markdown 与 SQLite backend 导出人类可读审计视图。

## 本轮目标

新增原子 action board 契约，提供 `append_pending_action()` 与 `claim_next_ready_action()`，并优先让 SQLite backend 的 pending action append / claim 具备真正单事务语义。该契约为后续默认 SQLite、常驻 watch、FastAPI/SSE 并发场景打基础，同时保持 Markdown backend 与现有 Markdown workspace 行为兼容。

## 禁止做

- 不把默认 backend 切到 SQLite。
- 不删除 Markdown backend、Markdown parser 或现有 Markdown workspace 文件协议。
- 不做 FastAPI / React。
- 不做 Agents SDK。
- 不做文件上传摄入。
- 不做 sqlite-vec / RAG。
- 不新增任何 agent / tool / GUI 侧硬件执行入口。

## 安全红线

`agent` / `tool_loop` / `gui` / MCP 请求侧只能 append pending proposal。只有 `watch` 能 claim action 并执行；`watch` 仍是唯一加载 driver、运行 `SafetyGate.validate()`、调用 `driver.execute()` 的侧。

真实执行路径保持不变：

```text
proposal -> action board -> watch -> SafetyGate.validate() -> driver.execute(action)
```

## 验收标准

1. 默认 backend 仍是 `markdown`。
2. SQLite backend 下 pending action append / claim 具备原子语义。
3. `watch` 仍是唯一 claim + `SafetyGate` + `driver.execute` 侧。
4. `agent` / `tool_loop` / `gui` / MCP 不新增任何硬件执行入口。
5. Markdown backend 的 action board 行为与现有 `ACTIONS.md` 兼容。
6. `export-audit` 仍能导出 action board。
7. safety boundary 测试通过。
8. 全量 `pytest` 通过后再提交本地 commit。
