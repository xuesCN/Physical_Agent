# Session Handoff：B3.6 Action Lease / Failure Recovery

> 目的：记录本轮为 SQLite `in_progress` action 增加 lease / stale recovery，并让 watch 在 driver 执行异常时写入终态与反馈的实现范围、边界和验证结果。
>
> 结论：默认 backend 仍是 `markdown`；SQLite backend 仍需 `workspace.backend: sqlite` opt-in。`watch` 仍是唯一 claim + `SafetyGate` + `driver.execute` 执行侧；agent / tool / gui 仍只能 append pending action。

## 实际完成范围

- 新增 brief：
  - `docs/next-session-b3.6-action-lease-recovery.zh-CN.md`
- 扩展 `StateStore` action recovery API：
  - `claim_next_ready_action(*, claim_owner: str = "watch") -> Action | None`
  - `recover_stale_actions(max_age_s: float, *, claim_owner: str | None = None) -> int`
- `SqliteStateStore`：
  - actions 表新增 claim 元数据列：`claimed_at`、`claim_owner`、`attempts`。
  - 初始化时兼容旧 `state.db`，通过 `PRAGMA table_info(actions)` 检测缺失列并 `ALTER TABLE`。
  - `claim_next_ready_action()` 在单个 `BEGIN IMMEDIATE` 事务中恢复超时 `in_progress`、领取 pending、写入 lease 元数据并递增 `attempts`。
  - 新增 `recover_stale_actions()`，把超时 `in_progress` 恢复为 pending，保留 attempts，不触碰 completed / cancelled。
  - `read_actions()` 仍只暴露 pending / completed / cancelled，不暴露内部 `in_progress`。
- `MarkdownStateStore`：
  - `claim_next_ready_action()` 兼容新增 `claim_owner` 参数。
  - `recover_stale_actions()` 返回 0；文件协议下不承诺强 lease。
- `WatchRuntime`：
  - 每次 `step()` 开始先调用 `recover_stale_actions(300)`。
  - claim 时写入 `claim_owner="watch"`。
  - `driver.execute(action)` 抛异常时 mark cancelled，写入 failed feedback/log，并继续处理，不留下永久 `in_progress`。

## 新增 / 调整的 StateStore Action Recovery API

- `claim_next_ready_action(*, claim_owner: str = "watch")`：
  - SQLite：先释放超过默认 300 秒 lease 的 stale `in_progress`，再领取第一条 pending action。
  - Markdown：继续取出第一条 pending，不使用 owner。
- `recover_stale_actions(max_age_s, claim_owner=None)`：
  - SQLite：恢复 `status='in_progress'` 且 `claimed_at IS NULL` 或 `claimed_at <= now - max_age_s` 的 action。
  - `claim_owner` 为可选过滤器；watch 默认不传，表示恢复所有超时 lease。
  - Markdown：no-op，返回 0。

## SQLite Schema Migration 细节

`actions` 新 schema 在既有字段后增加：

```sql
claimed_at TEXT,
claim_owner TEXT,
attempts INTEGER DEFAULT 0
```

初始化时：

1. `CREATE TABLE IF NOT EXISTS actions (...)` 继续兼容新库。
2. `_ensure_action_claim_columns()` 使用 `PRAGMA table_info(actions)` 检查旧库。
3. 对缺失列执行 `ALTER TABLE actions ADD COLUMN ...`。
4. 将 `attempts IS NULL` 的旧行补为 0。
5. 新增 `idx_actions_status_claimed_at`，用于按状态和 lease 时间恢复。

旧 `state.db` 缺少 claim 列时，`initialize()` 后 `exists()` 和 `claim_next_ready_action()` 均可用。

## Watch 异常处理语义

- SafetyGate 拒绝路径不变：mark cancelled，写 failed feedback/log，不调用 driver。
- driver 正常返回：
  - `completed` -> mark completed。
  - `failed` / `cancelled` -> mark cancelled。
- `driver.execute(action)` 抛异常：
  - watch catch 异常。
  - 生成 `ActionResult(status="failed", message="Driver execute failed: ...")`。
  - mark action cancelled，清空 SQLite claim 元数据。
  - 写入 feedback latest/history 和 watch log。
  - 继续循环；不会把 action 留在 `in_progress`。

## Markdown / SQLite Backend 行为差异

- Markdown backend：
  - 仍以 Markdown workspace 文件为状态真源。
  - claim 仍是兼容封装：从 pending 栏移除第一条 action。
  - 不维护 `in_progress`、lease、attempts；`recover_stale_actions()` 返回 0。
- SQLite backend：
  - `state.db` 是 action board 真源。
  - pending -> in_progress -> completed/cancelled 是内部状态机。
  - `in_progress` 只存在 DB 内部；UI/audit/read_actions 仍只看到三栏。
  - stale recovery 只恢复 `in_progress`，不重放 completed / cancelled；恢复后的 action 仍必须重新经过 watch claim + SafetyGate + driver.execute。

## 测试命令和结果

目标测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_state_store.py
```

结果：`17 passed in 2.06s`

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_watch_runtime.py
```

结果：`2 passed in 0.88s`

相关集合：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_state_store.py tests\test_mcp_server.py tests\test_watch_runtime.py tests\test_e2e_sqlite_loop.py tests\test_tool_loop.py tests\test_safety_boundaries.py
```

结果：`30 passed in 6.76s`

全量测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果：`120 passed in 27.90s`

## 未完成事项

- 未把默认 backend 切到 SQLite。
- 未删除 Markdown backend / Markdown parser / Markdown renderer。
- 未做 Agents SDK。
- 未做 FastAPI / React / 常驻 watch 服务化。
- 未做文件上传摄入。
- 未做 sqlite-vec / RAG。
- 未新增任何 agent / tool / gui 侧硬件执行入口。

## 下一步建议

1. 默认 SQLite 切换评估：用真实 workspace 验证迁移、audit export、并发 watch、回滚体验后再决定是否改默认。
2. B4 structured memory：先做结构化记忆，不引入 RAG 执行捷径。
3. B4b 文件上传摄入：上传内容只作为不可信上下文进入提案侧，由其引出的 action 仍必须走 action board + watch + SafetyGate。
4. C1 FastAPI：等 action lease/recovery 契约稳定后再接服务端 API，避免请求侧绕过 watch。
