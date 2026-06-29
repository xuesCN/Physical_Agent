# Session Handoff：B3.5 / B4a SQLite Atomic Action API

> 目的：记录本轮为 `StateStore` action board 增加原子 append / claim 契约的实现范围、事务语义、安全边界和验证结果。
>
> 结论：Markdown backend 保持兼容；SQLite backend 的 pending action append 与 claim 已使用单事务写入 / 领取。默认 backend 仍是 `markdown`，SQLite 仍需 `workspace.backend: sqlite` opt-in；`watch` 仍是唯一 claim + `SafetyGate` + `driver.execute` 侧。

## 实际完成范围

- 新增本轮 brief：
  - `docs/next-session-b3.5-atomic-actions.zh-CN.md`
- 扩展 `StateStore` Protocol：
  - `append_pending_action(action: Action | dict[str, Any]) -> Action`
  - `claim_next_ready_action() -> Action | None`
  - `mark_action_completed(action: Action | dict[str, Any]) -> None`
  - `mark_action_cancelled(action: Action | dict[str, Any]) -> None`
- `MarkdownStateStore`：
  - `append_pending_action()` 通过读取现有 `ACTIONS.md`、追加 pending、再渲染写回实现。
  - `claim_next_ready_action()` 领取第一条 pending，并从 pending 栏移除。
  - `mark_action_completed()` / `mark_action_cancelled()` 将已领取 action 写入对应终态栏。
- `SqliteStateStore`：
  - `append_pending_action()` 使用 `BEGIN IMMEDIATE` 单事务 `INSERT` pending action。
  - `claim_next_ready_action()` 使用 `BEGIN IMMEDIATE` 单事务把一条 `pending` 更新为内部 `in_progress`。
  - `mark_action_completed()` / `mark_action_cancelled()` 把已领取 action 更新到 `completed` / `cancelled`。
  - `read_actions()` 对外仍只组装 `pending` / `completed` / `cancelled`，不暴露 `in_progress`。
- 接入点：
  - `AgentRuntime.run_task()` 改为逐条 `append_pending_action()`。
  - `ChatRuntime._append_actions()` 改为逐条 `append_pending_action()`。
  - `PhysicalAgentMCP.submit_task()` / `propose_action()` 改为 `append_pending_action()`。
  - `WatchRuntime.step()` 改为 `claim_next_ready_action()` -> `SafetyGate.validate()` -> `driver.execute()` -> mark completed/cancelled。

## Backend 行为差异

- Markdown backend：
  - 仍以 `ACTIONS.md` 为状态真源。
  - 原子接口是兼容封装，不承诺强并发；适合保持旧文件协议与测试行为。
  - claimed action 在 mark 之前不会出现在三栏中。
- SQLite backend：
  - `state.db` 仍是 action board 真源，WAL 保持启用。
  - append / claim / mark 均在单个写事务中更新 action row 与 `doc_state.actions` revision。
  - claim 使用内部 `status='in_progress'` 避免多个 watch 领取同一条 pending action；该状态不出现在现有 UI / audit 的三栏 action board 中。

## 安全边界

本轮没有新增 driver import、硬件 SDK 调用、agent/tool/gui 执行入口、FastAPI/React、Agents SDK、文件上传或 RAG。

执行路径保持：

```text
proposal -> action board -> watch -> SafetyGate.validate() -> driver.execute(action)
```

`agent` / `tool_loop` / MCP 只追加 pending proposal；`watch` 仍是唯一 claim、运行 `SafetyGate`、调用 `driver.execute` 的执行侧。

## 并发与事务语义

- SQLite `append_pending_action()`：
  - `BEGIN IMMEDIATE`
  - 计算下一 `seq`
  - `INSERT status='pending'`
  - 更新 `doc_state.actions`
- SQLite `claim_next_ready_action()`：
  - `BEGIN IMMEDIATE`
  - 按 `seq, id` 选择第一条 `pending`
  - 同事务更新为 `status='in_progress'`
  - 更新 `doc_state.actions`
  - 并发 watch 中只有一个调用能领取同一 action。
- SQLite mark：
  - `BEGIN IMMEDIATE`
  - 已存在 action 则更新终态；不存在时为了兼容插入终态记录。

## 测试命令和结果

相关窄测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_state_store.py tests\test_mcp_server.py tests\test_watch_runtime.py tests\test_e2e_sqlite_loop.py tests\test_tool_loop.py tests\test_safety_boundaries.py
```

结果：

```text
26 passed in 6.00s
```

相关矩阵：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_state_store.py tests\test_e2e_markdown_loop.py tests\test_e2e_sqlite_loop.py tests\test_chat_protocol.py tests\test_chat_runtime.py tests\test_watch_runtime.py tests\test_tool_loop.py tests\test_mcp_server.py tests\test_safety_boundaries.py
```

结果：

```text
35 passed in 7.16s
```

全量测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果：

```text
116 passed in 28.78s
```

## 未完成事项

- 未把默认 backend 切到 SQLite。
- 未删除 Markdown backend / parser / renderer。
- 未实现 FastAPI / React / SSE / 常驻 watch 服务化。
- 未做 Agents SDK。
- 未做文件上传摄入。
- 未做 sqlite-vec / RAG。
- 未新增任何 agent/tool/gui 侧硬件执行入口。

## 下一步建议

1. 默认 SQLite 切换评估：在更多真实 workspace 上验证迁移、audit export、并发 watch 与回滚体验。
2. B4 structured memory：先做结构化记忆，不引入 RAG 执行捷径。
3. B4b 文件上传摄入：上传内容只作为不可信上下文进入提案侧，由它引出的动作仍必须经过 action board + watch + SafetyGate。
4. C1 FastAPI：在本轮 action API 稳定后再接服务端端点和 SSE，避免请求侧绕过 watch。
