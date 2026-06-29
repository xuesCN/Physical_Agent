# Session Handoff：B2 SqliteStateStore Opt-in 第一阶段

> 目的：记录本轮新增 opt-in SQLite 状态后端与 Markdown -> SQLite 迁移命令的实现范围、边界和验证结果。
>
> 结论：`SqliteStateStore` 已可通过 `workspace.backend=sqlite` 显式启用；默认 backend 仍是 `markdown`。Markdown parser/renderers 未删除，`SAFETY.md` 继续作为安全规则文件真源，watch 仍是唯一 driver / SafetyGate / execute 侧。

## 实际完成范围

- 新增 `physical_agent/state/sqlite.py`：
  - 使用 Python 标准库 `sqlite3`，无新增重依赖。
  - 实现现有 `StateStore` Protocol 的初始化、读写 task/capabilities/world/actions/feedback/safety/chat/plan/memory/log 方法。
  - chat rolling summary 在 SQLite backend 下继续由 `compact_chat_messages()` 维护。
  - `SAFETY.md` 仍由 workspace 目录下的 Markdown 文件读写，不迁入 SQLite 真源。
- 扩展 `open_state_store()`：
  - `markdown` 仍返回 `MarkdownStateStore`。
  - `sqlite` 返回 `SqliteStateStore`。
  - 其他 backend 明确报错。
- 新增 CLI 命令：
  - `physical-agent migrate-md-to-sqlite --config physical-agent.yaml`
  - 读取现有 Markdown workspace，写入 `workspace/state.db`。
  - 命令不会自动修改 `workspace.backend`。
- 新增本轮 brief：
  - `docs/next-session-b2-sqlite-state-store.zh-CN.md`

## SQLite Schema

第一阶段 schema 保持最小可用：

```sql
CREATE TABLE doc_state (
  name TEXT PRIMARY KEY,
  revision INTEGER DEFAULT 1,
  payload TEXT,
  updated_at TEXT
);

CREATE TABLE actions (
  id TEXT PRIMARY KEY,
  robot TEXT,
  capability TEXT,
  params TEXT,
  reason TEXT,
  depends_on TEXT,
  status TEXT,
  result TEXT,
  seq INTEGER,
  created_at TEXT,
  updated_at TEXT
);

CREATE INDEX idx_actions_status ON actions(status, seq);

CREATE TABLE log_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT,
  actor TEXT,
  message TEXT
);

CREATE TABLE chat_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  role TEXT,
  content TEXT,
  created_at TEXT,
  metadata TEXT
);

CREATE TABLE memory_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  content TEXT,
  source TEXT,
  created_at TEXT
);
```

`doc_state` 存 task/capabilities/world/actions/feedback/chat/plan/memory/log 的 metadata、revision 和 JSON payload。`actions` 通过 `status` 组装 pending/completed/cancelled action board。

## Migration 命令

使用方式：

```powershell
physical-agent migrate-md-to-sqlite --config physical-agent.yaml
```

行为：

- 从当前配置的 `workspace.path` 读取 Markdown workspace。
- 迁移 task/capabilities/world/actions/feedback/safety/chat/plan/memory/log。
- 写入 `workspace/state.db`。
- 如果 `state.db` 已存在，默认失败；可显式加 `--overwrite` 替换。
- 命令完成后只提示手动设置 `workspace.backend: sqlite`，不会偷偷切配置。

## Backend 切换方式

默认配置仍是：

```yaml
workspace:
  path: ./workspace
  backend: markdown
```

显式启用 SQLite：

```yaml
workspace:
  path: ./workspace
  backend: sqlite
```

切换后 runtime 通过 `open_state_store()` 打开 `SqliteStateStore`，调用方仍走同一套 `StateStore` 方法。

## 测试覆盖

新增/更新测试覆盖：

- `tests/test_state_store.py`
  - 默认 backend 仍为 Markdown。
  - `backend=sqlite` 返回 `SqliteStateStore`。
  - unsupported backend 明确报错。
  - SQLite store 初始化、task/capabilities/world/actions/feedback/safety/chat/plan/memory/log 基本读写。
  - SQLite chat rolling summary。
  - Markdown -> SQLite CLI 迁移，且不修改配置 backend。
- `tests/test_e2e_sqlite_loop.py`
  - SQLite backend 下 submit task -> pending -> watch step -> feedback/world/actions 更新。
- `tests/test_tool_loop.py`
  - OpenAI-compatible tool_loop 在 SQLite backend 下 proposal-only 写入 pending action。
- 既有 Markdown/e2e/chat/watch/MCP/safety boundary 测试继续通过。

验证命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_state_store.py tests\test_e2e_markdown_loop.py tests\test_e2e_sqlite_loop.py tests\test_chat_protocol.py tests\test_chat_runtime.py tests\test_watch_runtime.py tests\test_tool_loop.py tests\test_mcp_server.py tests\test_safety_boundaries.py
```

结果：

```text
27 passed in 6.84s
```

全量：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果：

```text
108 passed in 28.11s
```

## 安全边界

本轮没有新增 driver import、硬件 SDK 调用、agent/tool 执行入口、FastAPI/React、Agents SDK 或文件上传摄入。

执行路径保持不变：

```text
proposal -> action board -> watch -> SafetyGate.validate() -> driver.execute(action)
```

`SAFETY.md` 保持文件真源。SQLite backend 只替换状态存储实现，不改变执行路径。

## 未完成事项

- 未把默认 backend 切到 SQLite。
- 未删除 Markdown parser/renderers。
- 未实现 `export_human_view()` / audit export。
- 未做 SQLite 原子领取 pending action、并发 claim 或 action append API。
- 未做 FastAPI/React、Agents SDK、文件上传摄入。

## 下一步建议

1. **B3 audit export**：从 SQLite JSON 状态导出人类可读审计视图，补回 Markdown 真源切换后的可 diff 审计体验。
2. **默认切换评估**：在更多矩阵测试和迁移回滚路径稳定后，再评估是否把默认 backend 从 Markdown 切到 SQLite。
3. **B4b 文件上传摄入**：只作为不可信上下文进入提案侧，任何由上传内容引出的动作仍必须经过 action board + watch + SafetyGate。
