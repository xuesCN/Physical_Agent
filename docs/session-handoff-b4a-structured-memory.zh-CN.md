# Session Handoff：B4a structured memory

> 目的：基于默认 SQLite backend，把 `MEMORY` 从朴素 notes 扩展为结构化、可过滤、可审计的记忆层。
>
> 结论：已完成结构化 memory notes；默认 backend 仍是 SQLite，显式 `backend: markdown` 仍可用。未引入 embeddings、sqlite-vec、RAG、文件上传、FastAPI/React 或 Agents SDK；未新增任何 agent / tool / gui 硬件执行入口。

## 实际完成范围

- 新增本轮 brief：
  - `docs/next-session-b4a-structured-memory.zh-CN.md`
- 新增共享 memory normalization / filtering：
  - `physical_agent/protocol/memory.py`
- 扩展 StateStore memory 契约：
  - `append_memory_note(content, source="chat")` 继续兼容。
  - 新增可选字段：`kind="note"`、`tags=None`、`importance=0`。
  - `read_memory()` 继续兼容；新增可选过滤参数：`kind`、`source`、`tags`、`limit`。
- SQLite backend：
  - `memory_notes` 扩展为 `content`、`kind`、`source`、`tags`、`importance`、`created_at`。
  - `tags` 使用 JSON 文本，仍只依赖标准库 `sqlite3`。
  - `initialize()` 会对旧 `memory_notes(content, source, created_at)` 表执行 `ALTER TABLE` 兼容迁移。
  - `state-check` 会报告缺失的 memory columns，但仍保持只读、不迁移。
- Markdown backend：
  - 保持 `MEMORY.md` 的 `## Notes` YAML 块格式。
  - parser / renderer 保留，读写时把旧 notes 规范化为固定字段。
- Audit / migration：
  - `export-audit` 的 `memory.json` 包含结构化字段。
  - `migrate-md-to-sqlite` 会迁移旧 Markdown notes，并补默认 `kind/tags/importance`。
- ChatRuntime / tool loop：
  - 仍只把有限 memory notes 放入 agent 上下文。
  - `SAFETY`、world、capabilities、feedback 仍实时从 state 读取。
  - memory 不进入 watch / SafetyGate 执行路径。
- 额外修复：
  - `physical_agent/mcp/server.py` 将 `AgentRuntime` 改为 `submit_task()` 内懒加载，避免 `tests/test_mcp_server.py` 单独运行时出现 import 环；工具能力不变。

## Memory Schema / API

结构化 note 形状：

```json
{
  "content": "string",
  "kind": "note",
  "source": "chat",
  "tags": [],
  "importance": 0,
  "created_at": "2026-01-01T00:00:00Z"
}
```

`created_at` 对旧数据缺失时保留为 `null`，不伪造时间。`limit` 返回过滤后的最新 N 条，并保持时间顺序。

## SQLite Migration 细节

新建库直接创建完整 `memory_notes` 表。旧库在 `SqliteStateStore.initialize()` 中补列：

- `kind TEXT DEFAULT 'note'`
- `tags TEXT DEFAULT '[]'`
- `importance INTEGER DEFAULT 0`

同时补空值默认：

- 空 `kind` -> `note`
- 空 `source` -> `chat`
- 空 `tags` -> `[]`
- 空 `importance` -> `0`

## Markdown 兼容方式

`MEMORY.md` 继续使用现有 front matter + `## Notes` YAML fenced block。旧 notes 读取后会被规范化为固定字段；结构化字段直接写入 YAML，不需要新增 Markdown 文件或删除 parser / renderer。

## ChatRuntime / Tool Loop 上下文变化

上下文仍沿用原先行为：agent context 中只放最近有限 memory notes。新增测试确认 25 条 memory 中只进入最后 20 条；同时 live capabilities/world/feedback 不受 memory 中的 `unsafe_execute` 或 stale world 文本影响。

## 测试命令和结果

相关集合：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_chat_protocol.py tests\test_state_store.py tests\test_backend_matrix.py tests\test_chat_runtime.py tests\test_tool_loop.py tests\test_safety_boundaries.py
```

结果：

```text
49 passed in 10.30s
```

MCP 单测：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_mcp_server.py
```

结果：

```text
3 passed in 0.25s
```

全量测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果：

```text
137 passed in 30.69s
```

## 未完成事项

- 未做 embeddings。
- 未做 sqlite-vec。
- 未做 RAG。
- 未做文件上传摄入。
- 未做 FastAPI / React。
- 未做 Agents SDK。
- 未新增任何 agent / tool / gui 侧硬件执行入口。
- 未改变 watch / SafetyGate 执行边界。

## 下一步建议

1. B4b 文件上传摄入：上传内容作为不可信上下文，只进入 agent 提案侧。
2. B4c sqlite-vec 可选检索：在结构化 memory 稳定后再考虑 embedding / sqlite-vec，且只影响提案上下文。
3. C1 FastAPI：在 StateStore、audit、action board 契约继续稳定后做服务端 API。
