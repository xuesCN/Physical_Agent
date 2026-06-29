# Session Handoff：B3.7 SQLite default-readiness / backend matrix

> 目的：记录本轮为 SQLite 默认切换前补齐 backend matrix、迁移/readiness 验证、只读 state-check 诊断与 readiness 判断的实现范围、边界和测试结果。
>
> 结论：默认 backend 仍是 `markdown`；SQLite backend 仍需 `workspace.backend: sqlite` opt-in。B3.7 证据支持进入下一阶段默认 SQLite 切换工作，但本轮没有切默认、没有删除 Markdown。`watch` 仍是唯一 claim + `SafetyGate` + `driver.execute` 执行侧。

## 实际完成范围

- 新增本轮 brief：
  - `docs/next-session-b3.7-sqlite-readiness.zh-CN.md`
- 新增 backend matrix 测试：
  - `tests/test_backend_matrix.py`
  - 通过 `markdown` / `sqlite` 参数化 helper 覆盖同一组核心行为。
- 新增只读诊断：
  - `physical_agent/state/check.py`
  - CLI：`physical-agent state-check --config physical-agent.yaml`
- 新增 readiness 文档：
  - `docs/sqlite-readiness.zh-CN.md`

## Backend Matrix 覆盖情况

矩阵覆盖 `markdown` / `sqlite` 两个 backend：

- init / `store.exists()`；
- `append_pending_action()` proposal append；
- MCP `PhysicalAgentMCP.propose_action()` proposal-only 写 pending；
- ChatRuntime rule-based proposal，只写 pending，不执行 watch；
- WatchRuntime 成功执行；
- SafetyGate 拒绝路径；
- driver exception 路径，写 failed feedback 并终态 cancelled；
- `export_human_view()` audit export；
- CLI `export-audit` 不修改 config backend / action board；
- CLI `state-check` 不初始化 workspace、不执行 watch、不修改 action board。

迁移/readiness 覆盖：

- Markdown -> SQLite 迁移后，task / capabilities / world / actions / feedback / chat running_summary / memory / log 均可由 SQLite 读出；
- 迁移后切到 SQLite backend 可导出 audit view；
- `migrate-md-to-sqlite` 不修改 config backend；
- SQLite 旧 `state.db` 缺失 lease columns 时，既有自动迁移测试继续覆盖；
- `state-check` 可发现旧 SQLite schema 缺失 `claimed_at` / `claim_owner` / `attempts`，且不会自行迁移。

## Readiness 结论

`docs/sqlite-readiness.zh-CN.md` 的结论是：建议进入下一阶段默认 SQLite 切换，但作为单独小变更完成；本轮不切默认。

建议默认切换阶段继续保留：

- Markdown backend；
- Markdown parser/renderer；
- `migrate-md-to-sqlite`；
- `export-audit`；
- `state-check`；
- 明确的回滚说明。

主要剩余风险是：真实历史 workspace 的手写 Markdown 边界格式、默认 SQLite 后人类直接编辑 Markdown 不再改变真源、以及未来 C1/C2 服务化后的长时间并发行为。

## 新增 CLI

新增：

```powershell
physical-agent state-check --config physical-agent.yaml
```

输出：

- current backend；
- workspace path；
- workspace initialized；
- SQLite schema complete（Markdown 下为 `n/a`）；
- audit directory；
- audit export writable。

边界：

- 不调用 `WatchRuntime`；
- 不 claim action；
- 不运行 `SafetyGate`；
- 不调用 `driver.execute`；
- 不初始化 workspace；
- 不修改 backend/action board。

## 安全边界

本轮没有新增任何 agent/tool/gui 侧硬件执行入口。没有做 Agents SDK、FastAPI/React、文件上传摄入、sqlite-vec/RAG，也没有改变 OpenAI/tool_loop/rolling summary/audit export/action lease 行为。

执行路径保持：

```text
proposal -> action board -> watch -> SafetyGate.validate() -> driver.execute(action)
```

## 测试命令和结果

相关矩阵与回归：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_backend_matrix.py tests\test_state_store.py tests\test_mcp_server.py tests\test_watch_runtime.py tests\test_e2e_markdown_loop.py tests\test_e2e_sqlite_loop.py tests\test_tool_loop.py
```

结果：

```text
44 passed in 11.62s
```

Safety boundary：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_safety_boundaries.py
```

结果：

```text
1 passed in 0.12s
```

全量：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果：

```text
134 passed in 33.95s
```

## 未完成事项

- 未把默认 backend 切到 SQLite。
- 未删除 Markdown backend / parser / renderer。
- 未做 Agents SDK。
- 未做 FastAPI / React / 常驻 watch 服务化。
- 未做文件上传摄入。
- 未做 sqlite-vec / RAG。
- 未新增任何 agent/tool/gui 侧硬件执行入口。
- 未在真实历史 workspace 集合上做人工迁移抽样。

## 下一步建议

1. 默认 SQLite 切换：单独小变更修改默认 backend，并保留 Markdown 回滚路径；继续跑 backend matrix、safety boundary、全量 pytest。
2. B4 structured memory：在默认切换稳定后推进结构化记忆；不要引入 RAG 执行捷径。
3. C1 FastAPI：等默认 backend 与 action board 契约稳定后再做服务端 API，避免请求侧绕过 watch。
