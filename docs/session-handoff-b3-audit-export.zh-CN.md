# Session Handoff：B3 Audit Export / Human View

> 目的：记录本轮为 `StateStore` backends 增加人类可读 audit export 的实现范围、边界和验证结果。
>
> 结论：Markdown 与 SQLite backend 都支持显式 audit export。默认 backend 仍是 `markdown`；SQLite 仍需 `workspace.backend: sqlite` opt-in；Markdown parser/renderers 未删除；`SAFETY.md` 继续作为安全规则文件真源；watch 仍是唯一 driver / SafetyGate / execute 侧。

## 实际完成范围

- 扩展 `StateStore` Protocol：
  - 新增 `export_human_view(out_dir: Path | None = None) -> dict[str, Any]`。
- 新增公共 audit export helper：
  - `physical_agent/state/audit.py`
  - 负责稳定 pretty JSON 输出、默认 audit 目录、`SAFETY.md` 复制、Markdown log 解析。
- `MarkdownStateStore.export_human_view()`：
  - 通过现有 Markdown parser/read 接口读取 task/capabilities/world/actions/feedback/chat/plan/memory。
  - 从 `LOG.md` 解析 log entries。
  - 复制 `SAFETY.md` 到 audit 输出目录。
- `SqliteStateStore.export_human_view()`：
  - 从 SQLite JSON 状态和表读取 task/capabilities/world/actions/feedback/chat/plan/memory/log。
  - `actions` 来自 `actions` 表。
  - `chat` 来自 `chat_messages` 表和 `doc_state.chat.running_summary`。
  - `memory` 来自 `memory_notes` 表。
  - `log` 来自 `log_entries` 表；`LOG.md` 的兼容写入不再是 audit export 的读取来源。
  - `SAFETY.md` 仍作为文件真源复制。
- 新增 CLI 命令：
  - `physical-agent export-audit --config physical-agent.yaml [--out workspace/audit]`
  - 命令只读取当前配置的 backend 并导出 audit view，不初始化 workspace、不改变 backend、不执行 watch。
- 新增本轮 brief：
  - `docs/next-session-b3-audit-export.zh-CN.md`

## Audit Export 输出目录和格式

默认输出目录：

```text
workspace/audit/
```

可通过 `--out` 或 `export_human_view(out_dir=...)` 覆盖。

输出文件：

```text
manifest.json
task.json
capabilities.json
world.json
actions.json
feedback.json
chat.json
plan.json
memory.json
log.json
SAFETY.md
```

JSON 使用 `indent=2`、`sort_keys=True`、UTF-8，避免动态导出时间戳，便于 git diff。`SAFETY.md` 是文件真源的复制件，不替代 workspace 根目录下的 `SAFETY.md`。

## CLI 使用方式

默认导出到当前 workspace 的 `audit/`：

```powershell
physical-agent export-audit --config physical-agent.yaml
```

指定输出目录：

```powershell
physical-agent export-audit --config physical-agent.yaml --out workspace/audit
```

`--out` 为相对路径时按 config 文件所在目录解析。

## SQLite / Markdown Backend 行为差异

- Markdown backend：
  - Markdown workspace 文件仍是状态真源。
  - Export 通过现有 parser/read 接口生成 JSON audit view。
  - `LOG.md` 被解析为 `log.json`。
- SQLite backend：
  - `state.db` 是 task/capabilities/world/actions/feedback/chat/plan/memory/log 的状态真源。
  - Export 从 DB 中的 JSON payload 和结构化表生成 JSON audit view。
  - `append_log()` 仍兼容写 `LOG.md`，但 audit export 明确从 `log_entries` 表读取 log。
  - `SAFETY.md` 仍不迁入 SQLite，继续作为文件真源复制。

## 安全边界

本轮没有新增 driver import、硬件 SDK 调用、agent/tool 执行入口、FastAPI/React、Agents SDK 或文件上传摄入。

Audit export 是只读状态导出视图，不是真实执行入口。命令不调用 watch、不运行 `SafetyGate`、不调用 `driver.execute`。

真实执行路径保持不变：

```text
proposal -> action board -> watch -> SafetyGate.validate() -> driver.execute(action)
```

## 测试命令和结果

相关测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_state_store.py tests\test_e2e_markdown_loop.py tests\test_e2e_sqlite_loop.py tests\test_chat_protocol.py tests\test_chat_runtime.py tests\test_watch_runtime.py tests\test_tool_loop.py tests\test_mcp_server.py tests\test_safety_boundaries.py
```

结果：

```text
31 passed in 7.14s
```

全量测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果：

```text
112 passed in 27.71s
```

## 未完成事项

- 未把默认 backend 切到 SQLite。
- 未删除 Markdown parser/renderers。
- 未实现 SQLite 原子领取 pending action、并发 claim 或 action append API。
- 未做 FastAPI/React。
- 未做 Agents SDK。
- 未做文件上传摄入。
- 未新增任何 agent/tool 侧硬件执行入口。

## 下一步建议

1. **默认切换评估**：在更多真实 workspace 上验证迁移、导出、回滚体验后，再评估是否把默认 backend 从 Markdown 切到 SQLite。
2. **SQLite 原子 action API**：实现 `append_pending_action()` / `claim_next_ready_action()`，减少并发 watch 或服务化后的竞态。
3. **B4b 文件上传摄入**：只作为不可信上下文进入提案侧；任何由上传内容引出的动作仍必须经过 action board + watch + SafetyGate。
