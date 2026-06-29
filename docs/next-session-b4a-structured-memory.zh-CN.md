# Next Session Brief：B4a structured memory

## 背景

B3.8 已把新项目默认 StateStore backend 切到 SQLite；显式 `workspace.backend: markdown` 的项目仍可继续使用 Markdown backend。当前 `MEMORY` 仍是简单 notes：主要字段为 `content`、`source`、`created_at`，缺少结构化分类、标签、重要性和确定性过滤。

## 本轮目标

- 将 memory notes 扩展为结构化、可过滤、可审计的数据层。
- 支持 `kind`、`source`、`tags`、`importance`、`created_at` 等字段。
- 保持 `append_memory_note(content, source="chat")` 兼容。
- 提供确定性过滤能力，例如按 `kind`、`source`、`tags`、`limit` 读取。
- 默认 SQLite backend 作为主要实现路径，同时保持 Markdown backend 可用。

## 禁止做

- 不引入 embeddings。
- 不引入 sqlite-vec。
- 不做 RAG。
- 不做文件上传摄入。
- 不做 FastAPI / React。
- 不做 Agents SDK。
- 不新增任何 agent / tool / gui 侧硬件执行入口。

## 安全红线

- memory 只影响 agent 提案上下文。
- `SAFETY`、world、actions、approval 等安全关键事实仍必须实时读取 state。
- `watch` 与 `SafetyGate` 不依赖 memory。
- action 执行路径仍是 action proposal -> action board -> watch -> `SafetyGate.validate()` -> `driver.execute()`。

## 验收标准

1. 默认 backend 仍是 SQLite。
2. 显式 `backend: markdown` 仍可用。
3. memory notes 支持结构化字段和确定性过滤。
4. SQLite 旧 `memory_notes` schema 可自动迁移。
5. Markdown `MEMORY.md` 旧格式兼容，新增字段可审计。
6. Markdown -> SQLite 迁移后 memory 字段完整，旧 notes 自动补默认字段。
7. `export-audit` 的 `memory.json` 包含结构化字段。
8. ChatRuntime / tool loop 仍只放有限 memory notes 进 agent 上下文。
9. memory 不作为 watch / SafetyGate 的安全事实来源。
10. 不引入 embeddings / sqlite-vec / RAG。
11. safety boundary 测试通过。
12. 全量 `pytest` 通过。
